from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Literal
from uuid import UUID

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
from app.models import (
    Photo,
    SessionEvidence,
    TeachingSession,
    User,
)
from app.services.photo.processing import PhotoProcessingService
from app.services.photo.service import PhotoService
from app.services.photo.storage.local import LocalPrivatePhotoStorage
from app.services.session_evidence.service import (
    DuplicateSessionEvidenceError,
    PhotoInput,
    PhotoNotFoundError,
    SessionEvidenceNotFoundError,
    SessionEvidenceService,
    SessionNotEditableError,
    TeachingSessionNotFoundError,
)


router = APIRouter(
    prefix="/api/v1/sessions",
    tags=["Session Evidence"],
)


class SessionEvidenceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    teaching_session_id: UUID
    photo_id: UUID
    data_origin: Literal[
        "PRODUCTION",
        "DEMO",
        "TEST",
    ]
    created_at: datetime
    updated_at: datetime


def _get_photo_service() -> PhotoService:
    """
    Construct the application PhotoService.

    V1 uses private local filesystem storage.
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

    if teaching_session is None:
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


def _get_session_evidence(
    session_id: UUID,
    evidence_id: UUID,
    current_user: User,
    db: Session,
) -> tuple[TeachingSession, SessionEvidence]:
    """
    Get evidence belonging specifically to the
    teaching session in the URL.
    """

    teaching_session = _get_session(
        session_id=session_id,
        current_user=current_user,
        db=db,
    )

    evidence = (
        db.query(SessionEvidence)
        .filter(
            SessionEvidence.id == evidence_id,
            SessionEvidence.teaching_session_id
            == teaching_session.id,
        )
        .first()
    )

    if evidence is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session evidence not found.",
        )

    return teaching_session, evidence


def _serialize_session_evidence(
    evidence: SessionEvidence,
) -> SessionEvidenceResponse:
    return SessionEvidenceResponse(
        id=evidence.id,
        teaching_session_id=evidence.teaching_session_id,
        photo_id=evidence.photo_id,
        data_origin=evidence.data_origin,
        created_at=evidence.created_at,
        updated_at=evidence.updated_at,
    )


def _build_photo_input(
    *,
    photo: UploadFile | None,
    captured_at: datetime | None,
    latitude: Decimal | None,
    longitude: Decimal | None,
) -> PhotoInput:
    """
    Convert multipart photo fields into PhotoInput.

    Session evidence always requires a photo.
    """

    if photo is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A session evidence photo is required.",
        )

    if captured_at is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="captured_at is required.",
        )

    if latitude is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="latitude is required.",
        )

    if longitude is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="longitude is required.",
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

    if isinstance(
        exc,
        (
            TeachingSessionNotFoundError,
            SessionEvidenceNotFoundError,
            PhotoNotFoundError,
        ),
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    if isinstance(
        exc,
        (
            SessionNotEditableError,
            DuplicateSessionEvidenceError,
        ),
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    raise exc


def _compensate_failed_transaction(
    db: Session,
    service: SessionEvidenceService,
    operation,
) -> None:
    """
    Roll back the database transaction and remove any
    newly-created physical photo objects.
    """

    db.rollback()

    if operation is not None:
        service.compensate_new_storage(
            operation.new_storage_keys,
        )


# ------------------------------------------------------------------
# GET
# ------------------------------------------------------------------

@router.get(
    "/{session_id}/evidence",
    response_model=SessionEvidenceResponse,
)
def get_session_evidence(
    session_id: UUID,
    current_user: User = Depends(
        require_permission("session_evidence.view"),
    ),
    db: Session = Depends(get_db),
) -> SessionEvidenceResponse:

    _get_session(
        session_id=session_id,
        current_user=current_user,
        db=db,
    )

    service = SessionEvidenceService(
        photo_service=_get_photo_service(),
    )

    try:
        evidence = service.get(
            db=db,
            teaching_session_id=session_id,
        )

    except (
        TeachingSessionNotFoundError,
        SessionEvidenceNotFoundError,
    ) as exc:
        _raise_service_http_error(exc)

    return _serialize_session_evidence(evidence)


# ------------------------------------------------------------------
# GET ONE
# ------------------------------------------------------------------

@router.get(
    "/{session_id}/evidence/{evidence_id}",
    response_model=SessionEvidenceResponse,
)
def get_session_evidence_by_id(
    session_id: UUID,
    evidence_id: UUID,
    current_user: User = Depends(
        require_permission("session_evidence.view"),
    ),
    db: Session = Depends(get_db),
) -> SessionEvidenceResponse:

    _, evidence = _get_session_evidence(
        session_id=session_id,
        evidence_id=evidence_id,
        current_user=current_user,
        db=db,
    )

    return _serialize_session_evidence(evidence)


# ------------------------------------------------------------------
# CREATE
# ------------------------------------------------------------------

@router.post(
    "/{session_id}/evidence",
    response_model=SessionEvidenceResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_session_evidence(
    session_id: UUID,
    photo: UploadFile | None = File(None),
    captured_at: datetime | None = Form(None),
    latitude: Decimal | None = Form(None),
    longitude: Decimal | None = Form(None),
    current_user: User = Depends(
        require_permission("session_evidence.create"),
    ),
    db: Session = Depends(get_db),
) -> SessionEvidenceResponse:

    _get_session(
        session_id=session_id,
        current_user=current_user,
        db=db,
    )

    photo_input = _build_photo_input(
        photo=photo,
        captured_at=captured_at,
        latitude=latitude,
        longitude=longitude,
    )

    service = SessionEvidenceService(
        photo_service=_get_photo_service(),
    )

    operation = None

    try:
        operation = service.create(
            db=db,
            teaching_session_id=session_id,
            photo=photo_input,
        )

        db.commit()
        db.refresh(operation.session_evidence)

    except (
        TeachingSessionNotFoundError,
        SessionEvidenceNotFoundError,
        PhotoNotFoundError,
        SessionNotEditableError,
        DuplicateSessionEvidenceError,
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
            detail="Unable to create session evidence.",
        ) from exc

    except Exception:
        _compensate_failed_transaction(
            db,
            service,
            operation,
        )
        raise

    return _serialize_session_evidence(
        operation.session_evidence,
    )


# ------------------------------------------------------------------
# UPDATE / RETAKE
# ------------------------------------------------------------------

@router.patch(
    "/{session_id}/evidence",
    response_model=SessionEvidenceResponse,
)
def replace_session_evidence(
    session_id: UUID,
    photo: UploadFile | None = File(None),
    captured_at: datetime | None = Form(None),
    latitude: Decimal | None = Form(None),
    longitude: Decimal | None = Form(None),
    current_user: User = Depends(
        require_permission("session_evidence.update"),
    ),
    db: Session = Depends(get_db),
) -> SessionEvidenceResponse:

    _get_session(
        session_id=session_id,
        current_user=current_user,
        db=db,
    )

    photo_input = _build_photo_input(
        photo=photo,
        captured_at=captured_at,
        latitude=latitude,
        longitude=longitude,
    )

    service = SessionEvidenceService(
        photo_service=_get_photo_service(),
    )

    operation = None

    try:
        operation = service.replace(
            db=db,
            teaching_session_id=session_id,
            photo=photo_input,
        )

        db.commit()
        db.refresh(operation.session_evidence)

    except (
        TeachingSessionNotFoundError,
        SessionEvidenceNotFoundError,
        PhotoNotFoundError,
        SessionNotEditableError,
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
            detail="Unable to replace session evidence.",
        ) from exc

    except Exception:
        _compensate_failed_transaction(
            db,
            service,
            operation,
        )
        raise

    # Delete the old physical photo only after successful commit.
    if operation.obsolete_storage_keys:
        service.delete_obsolete_storage(
            operation.obsolete_storage_keys,
        )

    return _serialize_session_evidence(
        operation.session_evidence,
    )


# ------------------------------------------------------------------
# DELETE
# ------------------------------------------------------------------

@router.delete(
    "/{session_id}/evidence",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_session_evidence(
    session_id: UUID,
    current_user: User = Depends(
        require_permission("session_evidence.delete"),
    ),
    db: Session = Depends(get_db),
):
    _get_session(
        session_id=session_id,
        current_user=current_user,
        db=db,
    )

    service = SessionEvidenceService(
        photo_service=_get_photo_service(),
    )

    operation = None

    try:
        operation = service.delete(
            db=db,
            teaching_session_id=session_id,
        )

        db.commit()

    except (
        TeachingSessionNotFoundError,
        SessionEvidenceNotFoundError,
        SessionNotEditableError,
        PhotoNotFoundError,
    ) as exc:
        db.rollback()
        _raise_service_http_error(exc)

    except IntegrityError as exc:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Unable to delete session evidence.",
        ) from exc

    except Exception:
        db.rollback()
        raise

    # Delete physical storage only after successful DB commit.
    if operation.obsolete_storage_keys:
        service.delete_obsolete_storage(
            operation.obsolete_storage_keys,
        )

    return None