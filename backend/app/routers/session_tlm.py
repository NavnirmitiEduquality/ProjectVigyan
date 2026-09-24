from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Literal
from uuid import UUID
import pytest

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from pydantic import BaseModel, ConfigDict
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import (
    require_permission,
    require_school_access,
)
from app.models import SessionTLM, TeachingSession, User
from app.services.photo.processing import PhotoProcessingService
from app.services.photo.service import PhotoService
from app.services.photo.storage.local import LocalPrivatePhotoStorage
from app.services.session_tlm.service import (
    DuplicateTLMError,
    InactiveTLMError,
    InvalidQuantityError,
    InvalidTLMPhotoError,
    NAConflictError,
    PhotoInput,
    SessionNotEditableError,
    SessionTLMIntegrityError,
    SessionTLMNotFoundError,
    SessionTLMService,
    TeachingSessionNotFoundError,
    TLMNotFoundError,
)


router = APIRouter(
    prefix="/api/v1/sessions",
    tags=["Session TLM"],
)


class SessionTLMResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    teaching_session_id: UUID
    tlm_id: UUID
    tlm_name: str
    quantity: int
    usage: str | None
    photo_id: UUID | None
    data_origin: Literal[
        "PRODUCTION",
        "DEMO",
        "TEST",
    ]
    created_at: datetime
    updated_at: datetime


class SessionTLMListResponse(BaseModel):
    items: list[SessionTLMResponse]
    total: int


def _get_photo_service() -> PhotoService:
    """
    Construct the application PhotoService.

    V1 uses private local filesystem storage.
    The storage location can later be replaced by object storage
    without changing SessionTLM business logic.
    """

    processing_service = PhotoProcessingService()

    storage_root = Path("storage") / "photos"

    storage = LocalPrivatePhotoStorage(
        storage_root,
    )

    return PhotoService(
        processing_service=processing_service,
        storage=storage,
    )


def _get_session(
    session_id: UUID,
    current_user: User,
    db: Session,
) -> TeachingSession:
    """
    Get a teaching session and enforce school-level access.
    """

    teaching_session = (
        db.query(TeachingSession)
        .filter(
            TeachingSession.id == session_id,
        )
        .first()
    )

    if not teaching_session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Teaching session not found.",
        )

    require_school_access(
        school_id=(
            teaching_session.class_division.school_id
        ),
        current_user=current_user,
        db=db,
    )

    return teaching_session

def _get_session_tlm(
    session_id: UUID,
    session_tlm_id: UUID,
    current_user: User,
    db: Session,
) -> tuple[TeachingSession, SessionTLM]:
    """
    Get a SessionTLM belonging specifically to the
    teaching session in the URL.
    """

    teaching_session = _get_session(
        session_id=session_id,
        current_user=current_user,
        db=db,
    )

    session_tlm = (
        db.query(SessionTLM)
        .filter(
            SessionTLM.id == session_tlm_id,
            SessionTLM.teaching_session_id
            == teaching_session.id,
        )
        .first()
    )

    if not session_tlm:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session TLM not found.",
        )

    return teaching_session, session_tlm


def _serialize_session_tlm(
    session_tlm: SessionTLM,
) -> SessionTLMResponse:
    """
    Build the API representation from the database model.

    tlm_name comes from the TLM master relationship.
    """

    return SessionTLMResponse(
        id=session_tlm.id,
        teaching_session_id=session_tlm.teaching_session_id,
        tlm_id=session_tlm.tlm_id,
        tlm_name=session_tlm.tlm.name,
        quantity=session_tlm.quantity,
        usage=session_tlm.usage,
        photo_id=session_tlm.photo_id,
        data_origin=session_tlm.data_origin,
        created_at=session_tlm.created_at,
        updated_at=session_tlm.updated_at,
    )


def _build_photo_input(
    *,
    photo: UploadFile | None,
    captured_at: datetime | None,
    latitude: Decimal | None,
    longitude: Decimal | None,
) -> PhotoInput | None:
    """
    Convert multipart photo fields into the service-layer
    PhotoInput object.
    """

    if photo is None:
        if (
            captured_at is not None
            or latitude is not None
            or longitude is not None
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "captured_at, latitude and longitude "
                    "can only be provided with a photo."
                ),
            )

        return None

    if captured_at is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "captured_at is required when a photo "
                "is provided."
            ),
        )

    if latitude is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "latitude is required when a photo "
                "is provided."
            ),
        )

    if longitude is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "longitude is required when a photo "
                "is provided."
            ),
        )

    if photo.content_type not in {
        "image/jpeg",
        "image/jpg",
    }:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only JPEG photos are supported.",
        )

    try:
        image_bytes = photo.file.read()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unable to read the uploaded photo.",
        ) from exc

    return PhotoInput(
        image_bytes=image_bytes,
        captured_at=captured_at,
        latitude=latitude,
        longitude=longitude,
        original_filename=photo.filename,
    )


def _raise_service_http_error(
    exc: Exception,
) -> None:
    """
    Convert known service-layer exceptions to HTTP errors.
    """

    if isinstance(
        exc,
        (
            SessionTLMNotFoundError,
            TeachingSessionNotFoundError,
            TLMNotFoundError,
        ),
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    if isinstance(
        exc,
        (
            InvalidQuantityError,
            InvalidTLMPhotoError,
        ),
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    if isinstance(
        exc,
        (
            SessionNotEditableError,
            InactiveTLMError,
            DuplicateTLMError,
            NAConflictError,
            SessionTLMIntegrityError,
        ),
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    raise exc


def _compensate_failed_transaction(
    db: Session,
    service: SessionTLMService,
    operation,
) -> None:
    """
    Roll back the database transaction and remove any newly-created
    physical photo objects.
    """

    db.rollback()

    if operation is not None:
        service.compensate_new_storage(
            operation.new_storage_keys,
        )


# ------------------------------------------------------------------
# LIST
# ------------------------------------------------------------------

@router.get(
    "/{session_id}/tlms",
    response_model=SessionTLMListResponse,
)
def list_session_tlms(
    session_id: UUID,
    current_user: User = Depends(
        require_permission("session_tlm.view"),
    ),
    db: Session = Depends(get_db),
) -> SessionTLMListResponse:
    """
    List all TLM records belonging to a teaching session.
    """

    teaching_session = _get_session(
        session_id=session_id,
        current_user=current_user,
        db=db,
    )

    session_tlms = (
        db.query(SessionTLM)
        .filter(
            SessionTLM.teaching_session_id
            == teaching_session.id,
        )
        .order_by(SessionTLM.created_at.asc())
        .all()
    )

    return SessionTLMListResponse(
        items=[
            _serialize_session_tlm(session_tlm)
            for session_tlm in session_tlms
        ],
        total=len(session_tlms),
    )


# ------------------------------------------------------------------
# GET ONE
# ------------------------------------------------------------------

@router.get(
    "/{session_id}/tlms/{session_tlm_id}",
    response_model=SessionTLMResponse,
)
def get_session_tlm(
    session_id: UUID,
    session_tlm_id: UUID,
    current_user: User = Depends(
        require_permission("session_tlm.view"),
    ),
    db: Session = Depends(get_db),
) -> SessionTLMResponse:
    """
    Get one SessionTLM record.
    """

    _, session_tlm = _get_session_tlm(
        session_id=session_id,
        session_tlm_id=session_tlm_id,
        current_user=current_user,
        db=db,
    )

    return _serialize_session_tlm(session_tlm)


# ------------------------------------------------------------------
# CREATE
# ------------------------------------------------------------------

@router.post(
    "/{session_id}/tlms",
    response_model=SessionTLMResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_session_tlm(
    session_id: UUID,
    tlm_id: UUID = Form(...),
    quantity: int = Form(...),
    usage: str | None = Form(None),
    photo: UploadFile | None = File(None),
    captured_at: datetime | None = Form(None),
    latitude: Decimal | None = Form(None),
    longitude: Decimal | None = Form(None),
    current_user: User = Depends(
        require_permission("session_tlm.create"),
    ),
    db: Session = Depends(get_db),
) -> SessionTLMResponse:
    """
    Add TLM usage to an in-progress teaching session.
    """

    _get_session(
        session_id=session_id,
        current_user=current_user,
        db=db,
    )

    usage = usage.strip() if usage else None
    usage = usage or None

    photo_input = _build_photo_input(
        photo=photo,
        captured_at=captured_at,
        latitude=latitude,
        longitude=longitude,
    )

    service = SessionTLMService(
        photo_service=_get_photo_service(),
    )

    operation = None

    try:
        operation = service.create(
            db=db,
            teaching_session_id=session_id,
            tlm_id=tlm_id,
            quantity=quantity,
            usage=usage,
            photo=photo_input,
        )

        db.commit()
        db.refresh(operation.session_tlm)

    except (
        SessionTLMNotFoundError,
        TeachingSessionNotFoundError,
        TLMNotFoundError,
        InvalidQuantityError,
        InvalidTLMPhotoError,
        SessionNotEditableError,
        InactiveTLMError,
        DuplicateTLMError,
        NAConflictError,
        SessionTLMIntegrityError,
    ) as exc:
        _compensate_failed_transaction(
            db,
            service,
            operation,
        )
        _raise_service_http_error(exc)

    except IntegrityError as exc:
        _compensate_failed_transaction(
            db,
            service,
            operation,
        )

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Unable to create Session TLM.",
        ) from exc

    except Exception:
        _compensate_failed_transaction(
            db,
            service,
            operation,
        )
        raise

    return _serialize_session_tlm(
        operation.session_tlm,
    )


# ------------------------------------------------------------------
# UPDATE
# ------------------------------------------------------------------

@router.patch(
    "/{session_id}/tlms/{session_tlm_id}",
    response_model=SessionTLMResponse,
)
def update_session_tlm(
    session_id: UUID,
    session_tlm_id: UUID,
    tlm_id: UUID | None = Form(None),
    quantity: int | None = Form(None),
    usage: str | None = Form(None),
    photo: UploadFile | None = File(None),
    remove_photo: bool = Form(False),
    captured_at: datetime | None = Form(None),
    latitude: Decimal | None = Form(None),
    longitude: Decimal | None = Form(None),
    current_user: User = Depends(
        require_permission("session_tlm.update"),
    ),
    db: Session = Depends(get_db),
) -> SessionTLMResponse:
    """
    Update TLM usage while the session is editable.
    """

    _get_session_tlm(
        session_id=session_id,
        session_tlm_id=session_tlm_id,
        current_user=current_user,
        db=db,
    )

    if photo is not None and remove_photo:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "photo and remove_photo cannot be "
                "provided together."
            ),
        )

    usage = usage.strip() if usage is not None else None
    usage = usage or None

    photo_input = _build_photo_input(
        photo=photo,
        captured_at=captured_at,
        latitude=latitude,
        longitude=longitude,
    )

    service = SessionTLMService(
        photo_service=_get_photo_service(),
    )

    operation = None

    try:
        operation = service.update(
            db=db,
            session_tlm_id=session_tlm_id,
            tlm_id=tlm_id,
            quantity=quantity,
            usage=usage,
            photo=photo_input,
            remove_photo=remove_photo,
        )

        db.commit()
        db.refresh(operation.session_tlm)

    except (
        SessionTLMNotFoundError,
        TeachingSessionNotFoundError,
        TLMNotFoundError,
        InvalidQuantityError,
        InvalidTLMPhotoError,
        SessionNotEditableError,
        InactiveTLMError,
        DuplicateTLMError,
        NAConflictError,
        SessionTLMIntegrityError,
    ) as exc:
        _compensate_failed_transaction(
            db,
            service,
            operation,
        )
        _raise_service_http_error(exc)

    except IntegrityError as exc:
        _compensate_failed_transaction(
            db,
            service,
            operation,
        )

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Unable to update Session TLM.",
        ) from exc

    except Exception:
        _compensate_failed_transaction(
            db,
            service,
            operation,
        )
        raise

    # Physical deletion happens only after the database commit.
    if operation.obsolete_storage_keys:
        service.cleanup_storage(
            operation.obsolete_storage_keys,
        )

    return _serialize_session_tlm(
        operation.session_tlm,
    )


# ------------------------------------------------------------------
# DELETE
# ------------------------------------------------------------------

@router.delete(
    "/{session_id}/tlms/{session_tlm_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_session_tlm(
    session_id: UUID,
    session_tlm_id: UUID,
    current_user: User = Depends(
        require_permission("session_tlm.delete"),
    ),
    db: Session = Depends(get_db),
):
    """
    Delete TLM usage from an editable teaching session.
    """

    _get_session_tlm(
        session_id=session_id,
        session_tlm_id=session_tlm_id,
        current_user=current_user,
        db=db,
    )

    service = SessionTLMService(
        photo_service=_get_photo_service(),
    )

    operation = None

    try:
        operation = service.delete(
            db=db,
            session_tlm_id=session_tlm_id,
        )

        db.commit()

    except (
        SessionTLMNotFoundError,
        TeachingSessionNotFoundError,
        SessionNotEditableError,
        InvalidTLMPhotoError,
        SessionTLMIntegrityError,
    ) as exc:
        db.rollback()
        _raise_service_http_error(exc)

    except IntegrityError as exc:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Unable to delete Session TLM.",
        ) from exc

    except Exception:
        db.rollback()
        raise

    # Delete physical storage only after successful DB commit.
    if operation.obsolete_storage_keys:
        service.cleanup_storage(
            operation.obsolete_storage_keys,
        )

    return None