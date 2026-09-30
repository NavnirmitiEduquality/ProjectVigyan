from __future__ import annotations

from datetime import date, datetime, time
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
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
    require_permission,
    require_school_access,
)
from app.models import (
    ClassDivision,
    SessionPlanContent,
    SessionPlanItem,
    SessionPlanWeek,
    TeachingSession,
    User,
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


router = APIRouter(
    prefix="/api/v1/session-plans",
    tags=["Session Plans"],
)


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


def _get_week_for_current_user(
    *,
    week_start_date: date,
    current_user: User,
    db: Session,
) -> SessionPlanWeek:
    """
    Retrieve the authenticated user's own planning week.

    Planning ownership is deliberately not client-controlled.
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
    current_user: User = Depends(
        require_permission("session_plan.view")
    ),
    db: Session = Depends(get_db),
):
    """
    Get the authenticated para-teacher's planning week.

    Only the authenticated user's planning scope is exposed.
    """

    week = _get_week_for_current_user(
        week_start_date=week_start_date,
        current_user=current_user,
        db=db,
    )

    authorized_school_ids = get_authorized_school_ids(
        current_user,
        db,
    )

    items_query = (
        db.query(SessionPlanItem)
        .join(
            ClassDivision,
            SessionPlanItem.class_division_id
            == ClassDivision.id,
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
                .filter(
                    ClassDivision.school_id.in_(
                        authorized_school_ids
                    )
                )
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
    """

    item = _get_item_with_school_scope(
        item_id=item_id,
        current_user=current_user,
        db=db,
    )

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

    _commit_or_conflict(
        db,
        "Unable to delete session planning item.",
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

    _get_item_with_school_scope(
        item_id=item_id,
        current_user=current_user,
        db=db,
    )

    service = _service()

    try:
        content = service.get_content(
            db,
            para_teacher_id=current_user.id,
            item_id=item_id,
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

    _get_item_with_school_scope(
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