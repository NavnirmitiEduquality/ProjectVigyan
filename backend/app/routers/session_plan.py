from __future__ import annotations

from datetime import date, datetime, time
from uuid import UUID
import re
from urllib.parse import quote

import logging
from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from fastapi.responses import StreamingResponse
from pathlib import Path
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import (
    get_authorized_school_ids,
    get_user_permission_codes,
    require_permission,
    require_school_access,
)
from app.models import (
    ClassDivision,
    Role,
    UserAssignment,
    UserRole,
    SessionPlanContent,
    SessionPlanItem,
    SessionPlanWeek,
    TeachingSession,
    User,
    SessionPlanAttachment,
)
from app.services.session_plan.service import (
    DuplicatePlanningItemError,
    DuplicateSequenceError,
    InvalidPlanningDateError,
    InvalidPlanningWeekError,
    MinimumWeeklySessionsError,
    MissingLessonPlanContentError,
    SessionPlanAccessError,
    SessionPlanAlreadyLinkedError,
    SessionPlanContentNotFoundError,
    SessionPlanItemLockedError,
    SessionPlanItemNotFoundError,
    SessionPlanService,
    SessionPlanWeekNotFoundError,
)
from app.services.session_plan.attachment_storage import (
    AttachmentValidationError,
    MAX_ATTACHMENT_SIZE_BYTES,
    SessionPlanAttachmentStorage,
)


router = APIRouter(
    prefix="/api/v1/session-plans",
    tags=["Session Plans"],
)
logger = logging.getLogger(__name__)

# ----------------------------------------------------------------------
# RESPONSE MODELS
# ----------------------------------------------------------------------


class SessionPlanWeekResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    para_teacher_id: UUID
    week_start_date: date
    week_end_date: date
    data_origin: str
    created_at: datetime
    updated_at: datetime


class SessionPlanItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    session_plan_week_id: UUID
    class_division_id: UUID
    planned_date: date
    planned_start_time: time | None
    planned_end_time: time | None
    sequence_no: int
    data_origin: str
    created_at: datetime
    updated_at: datetime


class SessionPlanContentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    session_plan_item_id: UUID
    content: str
    data_origin: str
    created_at: datetime
    updated_at: datetime


class SessionPlanAttachmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    session_plan_content_id: UUID
    original_filename: str
    content_type: str
    file_size_bytes: int
    data_origin: str
    created_at: datetime
    updated_at: datetime


class SessionPlanWeekDetailResponse(BaseModel):
    week: SessionPlanWeekResponse
    items: list[SessionPlanItemResponse]


class SessionPlanTeachingSessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    session_plan_item_id: UUID | None
    class_division_id: UUID
    para_teacher_id: UUID
    session_date: date
    planned_start_time: time | None
    planned_end_time: time | None
    actual_start_time: datetime | None
    actual_end_time: datetime | None
    duration_minutes: int | None
    status: str
    remarks: str | None
    feedback_submitted: bool
    submitted_at: datetime | None
    data_origin: str


# ----------------------------------------------------------------------
# REQUEST MODELS
# ----------------------------------------------------------------------


class SessionPlanWeekCreate(BaseModel):
    week_start_date: date


class SessionPlanItemCreate(BaseModel):
    session_plan_week_id: UUID
    class_division_id: UUID
    planned_date: date
    sequence_no: int = Field(gt=0)
    planned_start_time: time | None = None
    planned_end_time: time | None = None

    @model_validator(mode="after")
    def validate_planned_time_pair(self):
        start_time = self.planned_start_time
        end_time = self.planned_end_time

        if start_time is None and end_time is not None:
            raise ValueError(
                "planned_start_time is required when "
                "planned_end_time is provided."
            )

        if start_time is not None and end_time is None:
            raise ValueError(
                "planned_end_time is required when "
                "planned_start_time is provided."
            )

        if (
            start_time is not None
            and end_time is not None
            and end_time <= start_time
        ):
            raise ValueError(
                "planned_end_time must be later than "
                "planned_start_time."
            )

        return self


class SessionPlanItemUpdate(BaseModel):
    class_division_id: UUID | None = None
    planned_date: date | None = None
    sequence_no: int | None = Field(
        default=None,
        gt=0,
    )
    planned_start_time: time | None = None
    planned_end_time: time | None = None

    @model_validator(mode="after")
    def validate_planned_time_pair(self):
        start_time = self.planned_start_time
        end_time = self.planned_end_time

        # Both omitted means "leave the existing time unchanged".
        if start_time is None and end_time is None:
            return self

        if start_time is None or end_time is None:
            raise ValueError(
                "planned_start_time and planned_end_time "
                "must be provided together."
            )

        if end_time <= start_time:
            raise ValueError(
                "planned_end_time must be later than "
                "planned_start_time."
            )

        return self


class SessionPlanContentUpsert(BaseModel):
    content: str = Field(
        min_length=1,
        max_length=20000,
    )


# ----------------------------------------------------------------------
# SERVICE / ERROR HELPERS
# ----------------------------------------------------------------------


def _service() -> SessionPlanService:
    return SessionPlanService()


def _attachment_storage() -> SessionPlanAttachmentStorage:
    return SessionPlanAttachmentStorage()


def _attachment_content_disposition(filename: str) -> str:
    suffix = Path(filename).suffix.lower()

    ascii_stem = Path(filename).stem.encode(
        "ascii",
        errors="ignore",
    ).decode("ascii")

    ascii_stem = re.sub(
        r"[^A-Za-z0-9._ -]",
        "_",
        ascii_stem,
    ).strip(" .")

    if not ascii_stem:
        ascii_stem = "attachment"

    ascii_filename = f"{ascii_stem}{suffix}"

    encoded_filename = quote(filename, safe="")

    return (
        f'attachment; filename="{ascii_filename}"; '
        f"filename*=UTF-8''{encoded_filename}"
    )

def _read_attachment_upload(upload: UploadFile) -> bytes:
    chunks: list[bytes] = []
    total_size = 0

    try:
        while True:
            chunk = upload.file.read(64 * 1024)

            if not chunk:
                break

            total_size += len(chunk)

            if total_size > MAX_ATTACHMENT_SIZE_BYTES:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail="Attachment exceeds the 5 MiB limit.",
                )

            chunks.append(chunk)

    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unable to read attachment.",
        ) from exc

    return b"".join(chunks)


def _raise_service_http_error(
    exc: Exception,
) -> None:
    """
    Convert session-planning domain errors into API errors.

    The service remains unaware of HTTP.
    """

    if isinstance(
        exc,
        (
            SessionPlanWeekNotFoundError,
            SessionPlanItemNotFoundError,
            SessionPlanContentNotFoundError,
        ),
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )

    if isinstance(exc, SessionPlanAccessError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        )

    if isinstance(
        exc,
        (
            InvalidPlanningWeekError,
            InvalidPlanningDateError,
        ),
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

    if isinstance(
        exc,
        (
            DuplicatePlanningItemError,
            DuplicateSequenceError,
            SessionPlanItemLockedError,
            MinimumWeeklySessionsError,
            MissingLessonPlanContentError,
            SessionPlanAlreadyLinkedError,
        ),
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )

    if isinstance(exc, ValueError):
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        )

    raise exc


def _get_item_with_school_scope(
    *,
    item_id: UUID,
    current_user: User,
    db: Session,
) -> SessionPlanItem:
    """
    Retrieve a planning item and enforce current-user school scope.
    """

    row = (
        db.query(
            SessionPlanItem,
            ClassDivision.school_id,
        )
        .join(
            ClassDivision,
            SessionPlanItem.class_division_id == ClassDivision.id,
        )
        .filter(
            SessionPlanItem.id == item_id,
        )
        .first()
    )

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session planning item not found.",
        )

    item, school_id = row

    require_school_access(
        school_id,
        current_user,
        db,
    )

    return item


def _authorize_teacher_plan_view(
    *,
    requested_teacher_id: UUID,
    current_user: User,
    db: Session,
) -> User:
    """
    Authorize viewing a Para-Teacher's planning week.

    Own plans require session_plan.view.
    Other teachers' plans require session_plan.view_all.
    """

    target_teacher = (
        db.query(User)
        .join(UserRole, UserRole.user_id == User.id)
        .join(Role, Role.id == UserRole.role_id)
        .filter(
            User.id == requested_teacher_id,
            User.account_category == "PARA_TEACHER",
            User.status == "ACTIVE",
            UserRole.is_active.is_(True),
            Role.code == "PARA_TEACHER",
        )
        .first()
    )

    if target_teacher is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Active Para-Teacher not found.",
        )

    if requested_teacher_id != current_user.id:
        permissions = get_user_permission_codes(
            current_user,
            db,
        )

        if "session_plan.view_all" not in permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not authorized to view another Para-Teacher's plan.",
            )

    return target_teacher


def _authorize_teacher_week_school_scope(
    *,
    teacher_id: UUID,
    week_start_date: date,
    week_end_date: date,
    authorized_school_ids: set | None,
    db: Session,
) -> None:
    """
    Ensure a school-scoped viewer can access the target
    teacher's planning week through an overlapping assignment.
    """

    if authorized_school_ids is None:
        return

    if not authorized_school_ids:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Planning week not found.",
        )

    assignment = (
        db.query(UserAssignment.id)
        .filter(
            UserAssignment.user_id == teacher_id,
            UserAssignment.is_active.is_(True),
            UserAssignment.start_date <= week_end_date,
            (
                UserAssignment.end_date.is_(None)
                | (UserAssignment.end_date >= week_start_date)
            ),
            (
                (UserAssignment.scope_type == "PROJECT")
                | (
                    (UserAssignment.scope_type == "SCHOOL")
                    & UserAssignment.school_id.in_(authorized_school_ids)
                )
            ),
        )
        .first()
    )

    if assignment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Planning week not found.",
        )


def _get_item_owner_id(item: SessionPlanItem) -> UUID:
    return item.session_plan_week.para_teacher_id


def _get_item_for_authorized_view(
    *,
    item_id: UUID,
    current_user: User,
    db: Session,
) -> tuple[SessionPlanItem, UUID]:
    """
    Retrieve an item after checking school scope, plan ownership
    visibility, and teacher assignment scope.
    """

    item = _get_item_with_school_scope(
        item_id=item_id,
        current_user=current_user,
        db=db,
    )

    owner_id = _get_item_owner_id(item)
    week = item.session_plan_week

    _authorize_teacher_plan_view(
        requested_teacher_id=owner_id,
        current_user=current_user,
        db=db,
    )

    authorized_school_ids = get_authorized_school_ids(
        current_user,
        db,
    )

    _authorize_teacher_week_school_scope(
        teacher_id=owner_id,
        week_start_date=week.week_start_date,
        week_end_date=week.week_end_date,
        authorized_school_ids=authorized_school_ids,
        db=db,
    )

    return item, owner_id


def _get_week_for_current_user(
    *,
    week_start_date: date,
    current_user: User,
    db: Session,
) -> SessionPlanWeek:
    """
    Retrieve the authenticated user's own planning week.
    """

    service = _service()

    try:
        return service.get_week(
            db,
            para_teacher_id=current_user.id,
            week_start_date=week_start_date,
        )
    except Exception as exc:
        _raise_service_http_error(exc)
        raise


def _commit_or_conflict(
    db: Session,
    detail: str,
) -> None:
    try:
        db.commit()
    except IntegrityError:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=detail,
        )


# ----------------------------------------------------------------------
# WEEK
# ----------------------------------------------------------------------



@router.get(
    "/weeks/{week_start_date}",
    response_model=SessionPlanWeekDetailResponse,
)
def get_session_plan_week(
    week_start_date: date,
    para_teacher_id: UUID | None = None,
    current_user: User = Depends(
        require_permission("session_plan.view")
    ),
    db: Session = Depends(get_db),
):
    """
    Get the requested Para-Teacher's planning week.

    Cross-teacher visibility requires session_plan.view_all.
    Returned items are restricted to the user's authorized schools.
    """

    requested_teacher_id = para_teacher_id or current_user.id

    _authorize_teacher_plan_view(
        requested_teacher_id=requested_teacher_id,
        current_user=current_user,
        db=db,
    )

    service = _service()

    try:
        week = service.get_week(
            db,
            para_teacher_id=requested_teacher_id,
            week_start_date=week_start_date,
        )
    except Exception as exc:
        _raise_service_http_error(exc)
        raise

    authorized_school_ids = get_authorized_school_ids(
        current_user,
        db,
    )

    _authorize_teacher_week_school_scope(
        teacher_id=requested_teacher_id,
        week_start_date=week.week_start_date,
        week_end_date=week.week_end_date,
        authorized_school_ids=authorized_school_ids,
        db=db,
    )

    items_query = (
        db.query(SessionPlanItem)
        .join(
            ClassDivision,
            SessionPlanItem.class_division_id == ClassDivision.id,
        )
        .filter(
            SessionPlanItem.session_plan_week_id == week.id,
        )
    )

    if authorized_school_ids is not None:
        if not authorized_school_ids:
            items = []
        else:
            items = (
                items_query
                .filter(ClassDivision.school_id.in_(authorized_school_ids))
                .order_by(
                    SessionPlanItem.planned_date,
                    SessionPlanItem.sequence_no,
                )
                .all()
            )
    else:
        items = (
            items_query
            .order_by(
                SessionPlanItem.planned_date,
                SessionPlanItem.sequence_no,
            )
            .all()
        )

    return SessionPlanWeekDetailResponse(
        week=week,
        items=items,
    )


@router.post(
    "/weeks",
    response_model=SessionPlanWeekResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_session_plan_week(
    payload: SessionPlanWeekCreate,
    current_user: User = Depends(
        require_permission("session_plan.create")
    ),
    db: Session = Depends(get_db),
):
    """
    Get or create the authenticated para-teacher's planning week.
    """

    service = _service()

    try:
        week = service.get_or_create_week(
            db,
            para_teacher_id=current_user.id,
            week_start_date=payload.week_start_date,
            data_origin="PRODUCTION",
        )
    except Exception as exc:
        _raise_service_http_error(exc)
        raise

    _commit_or_conflict(
        db,
        "Unable to create session planning week.",
    )

    db.refresh(week)

    return week


# ----------------------------------------------------------------------
# ITEM
# ----------------------------------------------------------------------


@router.post(
    "/items",
    response_model=SessionPlanItemResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_session_plan_item(
    payload: SessionPlanItemCreate,
    current_user: User = Depends(
        require_permission("session_plan.create")
    ),
    db: Session = Depends(get_db),
):
    """
    Add a planned session to the authenticated user's planning week.
    """

    class_division = (
        db.query(ClassDivision)
        .filter(
            ClassDivision.id == payload.class_division_id,
        )
        .first()
    )

    if class_division is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Class division not found.",
        )

    require_school_access(
        class_division.school_id,
        current_user,
        db,
    )

    service = _service()

    try:
        item = service.create_item(
            db,
            para_teacher_id=current_user.id,
            session_plan_week_id=payload.session_plan_week_id,
            class_division_id=payload.class_division_id,
            planned_date=payload.planned_date,
            sequence_no=payload.sequence_no,
            planned_start_time=payload.planned_start_time,
            planned_end_time=payload.planned_end_time,
            data_origin="PRODUCTION",
        )
    except Exception as exc:
        _raise_service_http_error(exc)
        raise

    _commit_or_conflict(
        db,
        "Unable to create session planning item.",
    )

    db.refresh(item)

    return item


@router.patch(
    "/items/{item_id}",
    response_model=SessionPlanItemResponse,
)
def update_session_plan_item(
    item_id: UUID,
    payload: SessionPlanItemUpdate,
    current_user: User = Depends(
        require_permission("session_plan.update")
    ),
    db: Session = Depends(get_db),
):
    """
    Update an editable session planning item.
    """

    item = _get_item_with_school_scope(
        item_id=item_id,
        current_user=current_user,
        db=db,
    )

    # If the class/division is changing, enforce the target
    # class's school scope as well.
    if payload.class_division_id is not None:
        target_class_division = (
            db.query(ClassDivision)
            .filter(
                ClassDivision.id
                == payload.class_division_id,
            )
            .first()
        )

        if target_class_division is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Class division not found.",
            )

        require_school_access(
            target_class_division.school_id,
            current_user,
            db,
        )

    service = _service()

    try:
        updated_item = service.update_item(
            db,
            para_teacher_id=current_user.id,
            item_id=item.id,
            class_division_id=payload.class_division_id,
            planned_date=payload.planned_date,
            sequence_no=payload.sequence_no,
            planned_start_time=payload.planned_start_time,
            planned_end_time=payload.planned_end_time,
        )
    except Exception as exc:
        _raise_service_http_error(exc)
        raise

    _commit_or_conflict(
        db,
        "Unable to update session planning item.",
    )

    db.refresh(updated_item)

    return updated_item


@router.post(
    "/items/{item_id}/attachments",
    response_model=SessionPlanAttachmentResponse,
    status_code=status.HTTP_201_CREATED,
)
def upload_session_plan_attachment(
    item_id: UUID,
    attachment: UploadFile = File(...),
    current_user: User = Depends(
        require_permission("session_plan.update")
    ),
    db: Session = Depends(get_db),
):
    item = _get_item_with_school_scope(
        item_id=item_id,
        current_user=current_user,
        db=db,
    )

    service = _service()

    try:
        service.ensure_item_editable(
            db,
            para_teacher_id=current_user.id,
            item_id=item.id,
        )
        content = service.get_content(
            db,
            para_teacher_id=current_user.id,
            item_id=item.id,
        )
    except Exception as exc:
        _raise_service_http_error(exc)
        raise

    if not attachment.filename:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A filename is required.",
        )

    if len(attachment.filename) > 255:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Filename must not exceed 255 characters.",
        )

    data = _read_attachment_upload(attachment)
    storage = _attachment_storage()

    try:
        _, validated_content_type = storage.validate(
            attachment.filename,
            attachment.content_type or "",
            data,
        )
    except AttachmentValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    try:
        storage_key = storage.save(
            attachment.filename,
            validated_content_type,
            data,
        )
    except AttachmentValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    record = SessionPlanAttachment(
        session_plan_content_id=content.id,
        storage_key=storage_key,
        original_filename=Path(attachment.filename).name,
        content_type=validated_content_type,
        file_size_bytes=len(data),
        data_origin="PRODUCTION",
    )

    try:
        db.add(record)
        db.flush()
        db.refresh(record)

    except Exception:
        db.rollback()

        try:
            storage.delete(storage_key)
        except OSError:
            # Preserve the original database exception.
            # An orphaned file may require reconciliation.
            pass

        raise

    try:
        db.commit()

    except Exception as exc:
        db.rollback()

        try:
            storage.delete(storage_key)
        except OSError:
            # Preserve the original commit exception.
            # An orphaned file may require reconciliation.
            pass

        if isinstance(exc, IntegrityError):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Unable to save session-plan attachment.",
            ) from exc

        raise

    return record


@router.get(
    "/items/{item_id}/attachments",
    response_model=list[SessionPlanAttachmentResponse],
)
def list_session_plan_attachments(
    item_id: UUID,
    current_user: User = Depends(
        require_permission("session_plan.view")
    ),
    db: Session = Depends(get_db),
):
    item, owner_id = _get_item_for_authorized_view(
        item_id=item_id,
        current_user=current_user,
        db=db,
    )

    service = _service()

    try:
        content = service.get_content(
            db,
            para_teacher_id=owner_id,
            item_id=item.id,
        )
    except Exception as exc:
        _raise_service_http_error(exc)
        raise

    return (
        db.query(SessionPlanAttachment)
        .filter(
            SessionPlanAttachment.session_plan_content_id == content.id,
        )
        .order_by(SessionPlanAttachment.created_at.asc())
        .all()
    )


@router.get(
    "/items/{item_id}/attachments/{attachment_id}",
)
def download_session_plan_attachment(
    item_id: UUID,
    attachment_id: UUID,
    current_user: User = Depends(
        require_permission("session_plan.view")
    ),
    db: Session = Depends(get_db),
):
    item, owner_id = _get_item_for_authorized_view(
        item_id=item_id,
        current_user=current_user,
        db=db,
    )

    service = _service()

    try:
        content = service.get_content(
            db,
            para_teacher_id=owner_id,
            item_id=item.id,
        )
    except Exception as exc:
        _raise_service_http_error(exc)
        raise

    attachment = (
        db.query(SessionPlanAttachment)
        .filter(
            SessionPlanAttachment.id == attachment_id,
            SessionPlanAttachment.session_plan_content_id
            == content.id,
        )
        .first()
    )

    if attachment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session-plan attachment not found.",
        )

    storage = _attachment_storage()

    try:
        file_handle = storage.open(attachment.storage_key)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Attachment file is unavailable.",
        ) from exc
    except OSError as exc:
        logger.exception(
            "Unable to open session-plan attachment."
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to retrieve attachment.",
        ) from exc

    def file_iterator():
        try:
            while True:
                chunk = file_handle.read(64 * 1024)

                if not chunk:
                    break

                yield chunk
        finally:
            file_handle.close()

    return StreamingResponse(
        file_iterator(),
        media_type=attachment.content_type,
        headers={
            "Content-Disposition": _attachment_content_disposition(
                attachment.original_filename
            ),
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.delete(
    "/items/{item_id}/attachments/{attachment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_session_plan_attachment(
    item_id: UUID,
    attachment_id: UUID,
    current_user: User = Depends(
        require_permission("session_plan.update")
    ),
    db: Session = Depends(get_db),
):
    item = _get_item_with_school_scope(
        item_id=item_id,
        current_user=current_user,
        db=db,
    )

    service = _service()

    try:
        service.ensure_item_editable(
            db,
            para_teacher_id=current_user.id,
            item_id=item.id,
        )

        content = service.get_content(
            db,
            para_teacher_id=current_user.id,
            item_id=item.id,
        )
    except Exception as exc:
        _raise_service_http_error(exc)
        raise

    attachment = (
        db.query(SessionPlanAttachment)
        .filter(
            SessionPlanAttachment.id == attachment_id,
            SessionPlanAttachment.session_plan_content_id
            == content.id,
        )
        .first()
    )

    if attachment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session-plan attachment not found.",
        )

    storage_key = attachment.storage_key

    db.delete(attachment)

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Unable to delete session-plan attachment.",
        ) from exc
    except Exception:
        db.rollback()
        raise

    try:
        _attachment_storage().delete(storage_key)
    except OSError:
        logger.exception(
            "Unable to delete physical session-plan attachment "
            "after database deletion. Storage key: %s",
            storage_key,
        )

    return None


@router.delete(
    "/items/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_session_plan_item(
    item_id: UUID,
    current_user: User = Depends(
        require_permission("session_plan.delete")
    ),
    db: Session = Depends(get_db),
):
    """
    Delete an editable session planning item.

    Physical attachment files are deleted only after
    the database transaction succeeds.
    """

    item = _get_item_with_school_scope(
        item_id=item_id,
        current_user=current_user,
        db=db,
    )

    # Capture physical storage keys before deleting
    # the lesson-plan content and attachment records.
    attachment_keys = (
        db.query(SessionPlanAttachment.storage_key)
        .join(
            SessionPlanContent,
            SessionPlanAttachment.session_plan_content_id
            == SessionPlanContent.id,
        )
        .filter(
            SessionPlanContent.session_plan_item_id == item.id,
        )
        .all()
    )

    storage_keys = [row[0] for row in attachment_keys]

    service = _service()

    try:
        service.delete_item(
            db,
            para_teacher_id=current_user.id,
            item_id=item.id,
        )
    except Exception as exc:
        _raise_service_http_error(exc)
        raise

    # This commits the database deletion.
    # If it fails, the exception prevents physical cleanup.
    _commit_or_conflict(
        db,
        "Unable to delete session planning item.",
    )

    # Delete physical files only after successful commit.
    storage = _attachment_storage()

    for storage_key in storage_keys:
        try:
            storage.delete(storage_key)
        except OSError:
            logger.exception(
                "Unable to delete session-plan attachment file "
                "after item deletion. Storage key: %s",
                storage_key,
            )

    return None


# ----------------------------------------------------------------------
# LESSON PLAN CONTENT
# ----------------------------------------------------------------------


@router.get(
    "/items/{item_id}/content",
    response_model=SessionPlanContentResponse,
)
def get_session_plan_content(
    item_id: UUID,
    current_user: User = Depends(
        require_permission("session_plan.view")
    ),
    db: Session = Depends(get_db),
):
    """
    Get lesson-plan content for a planning item.
    """

    item, owner_id = _get_item_for_authorized_view(
        item_id=item_id,
        current_user=current_user,
        db=db,
    )

    service = _service()

    try:
        content = service.get_content(
            db,
            para_teacher_id=owner_id,
            item_id=item.id,
        )
    except Exception as exc:
        _raise_service_http_error(exc)
        raise

    return content


@router.put(
    "/items/{item_id}/content",
    response_model=SessionPlanContentResponse,
)
def set_session_plan_content(
    item_id: UUID,
    payload: SessionPlanContentUpsert,
    current_user: User = Depends(
        require_permission("session_plan.update")
    ),
    db: Session = Depends(get_db),
):
    """
    Create or replace lesson-plan content for an item.
    """

    _get_item_with_school_scope(
        item_id=item_id,
        current_user=current_user,
        db=db,
    )

    service = _service()

    try:
        content = service.set_content(
            db,
            para_teacher_id=current_user.id,
            item_id=item_id,
            content=payload.content,
            data_origin="PRODUCTION",
        )
    except Exception as exc:
        _raise_service_http_error(exc)
        raise

    _commit_or_conflict(
        db,
        "Unable to save lesson-plan content.",
    )

    db.refresh(content)

    return content


# ----------------------------------------------------------------------
# WEEK VALIDATION / TEACHING READINESS
# ----------------------------------------------------------------------


@router.post(
    "/items/{item_id}/validate",
    response_model=SessionPlanItemResponse,
)
def validate_session_plan_item(
    item_id: UUID,
    current_user: User = Depends(
        require_permission("session_plan.view")
    ),
    db: Session = Depends(get_db),
):
    """
    Validate that a planning item is ready to be linked
    to a TeachingSession.

    The service performs the actual readiness rules.
    """

    _get_item_for_authorized_view(
        item_id=item_id,
        current_user=current_user,
        db=db,
    )

    service = _service()

    try:
        item = service.ensure_ready_for_teaching_session(
            db,
            para_teacher_id=current_user.id,
            item_id=item_id,
        )
    except Exception as exc:
        _raise_service_http_error(exc)
        raise

    return item


# ----------------------------------------------------------------------
# TEACHING SESSION LINKING
# ----------------------------------------------------------------------


@router.post(
    "/items/{item_id}/teaching-session",
    response_model=SessionPlanTeachingSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_teaching_session_from_plan(
    item_id: UUID,
    current_user: User = Depends(
        require_permission("session.create")
    ),
    db: Session = Depends(get_db),
):
    """
    Create a TeachingSession from a validated session-plan item.

    The session-plan item remains the source of the planned
    class, date, teacher, and planned time values.

    The authenticated para-teacher is used as the session owner.
    """

    _get_item_with_school_scope(
        item_id=item_id,
        current_user=current_user,
        db=db,
    )

    service = _service()

    try:
        teaching_session = service.link_teaching_session(
            db,
            para_teacher_id=current_user.id,
            item_id=item_id,
        )
    except Exception as exc:
        _raise_service_http_error(exc)
        raise

    _commit_or_conflict(
        db,
        "Unable to create teaching session from session plan.",
    )

    db.refresh(teaching_session)

    return teaching_session