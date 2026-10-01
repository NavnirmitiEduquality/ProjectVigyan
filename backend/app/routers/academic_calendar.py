from __future__ import annotations

from datetime import date, datetime, time
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import (
    get_authorized_school_ids,
    require_permission,
    require_school_access,
)
from app.models import ClassDivision, SessionPlanItem, User
from app.services.academic_calendar.service import (
    AcademicCalendarError,
    AcademicCalendarService,
    AcademicHolidayAlreadyExistsError,
    AcademicHolidayNotFoundError,
    AcademicYearNotFoundError,
    ActiveAcademicYearNotFoundError,
)
from app.services.session_plan.service import (
    InvalidPlanningDateError,
    SessionPlanAccessError,
    SessionPlanItemLockedError,
    SessionPlanItemNotFoundError,
    SessionPlanService,
)


router = APIRouter(
    prefix="/api/v1/academic-calendar",
    tags=["Academic Calendar"],
)


class CalendarSessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    session_plan_item_id: UUID
    para_teacher_id: UUID
    class_division_id: UUID
    planned_start_time: time | None
    planned_end_time: time | None
    sequence_no: int
    teaching_session_id: UUID | None
    teaching_session_status: str | None
    derived_status: str


class CalendarDayResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    calendar_date: date
    is_working_day: bool
    is_holiday: bool
    holiday_name: str | None
    holiday_type: str | None
    sessions: list[CalendarSessionResponse]


class HolidayCreate(BaseModel):
    holiday_date: date
    name: str = Field(min_length=1, max_length=150)
    type: str = Field(min_length=1, max_length=50)
    description: str | None = None


class HolidayUpdate(BaseModel):
    holiday_date: date | None = None
    name: str | None = Field(default=None, min_length=1, max_length=150)
    type: str | None = Field(default=None, min_length=1, max_length=50)
    description: str | None = None
    is_active: bool | None = None


class HolidayResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    academic_year_id: UUID
    holiday_date: date
    name: str
    type: str
    description: str | None
    is_active: bool


class RescheduleRequest(BaseModel):
    planned_date: date
    planned_start_time: time | None = None
    planned_end_time: time | None = None

    @model_validator(mode="after")
    def validate_time_pair(self) -> RescheduleRequest:
        if (self.planned_start_time is None) != (
            self.planned_end_time is None
        ):
            raise ValueError(
                "planned_start_time and planned_end_time must be provided together."
            )
        if (
            self.planned_start_time is not None
            and self.planned_end_time is not None
            and self.planned_end_time <= self.planned_start_time
        ):
            raise ValueError(
                "planned_end_time must be later than planned_start_time."
            )
        return self


class PlanningComplianceResponse(BaseModel):
    para_teacher_id: UUID
    week_start_date: date
    planned_session_count: int
    minimum_required: int
    minimum_met: bool


def _raise_calendar_http_error(exc: Exception) -> None:
    if isinstance(
        exc,
        (
            AcademicYearNotFoundError,
            AcademicHolidayNotFoundError,
            ActiveAcademicYearNotFoundError,
            SessionPlanItemNotFoundError,
        ),
    ):
        raise HTTPException(status_code=404, detail=str(exc))
    if isinstance(
        exc,
        (
            AcademicHolidayAlreadyExistsError,
            SessionPlanItemLockedError,
        ),
    ):
        raise HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, (SessionPlanAccessError,)):
        raise HTTPException(status_code=403, detail=str(exc))
    if isinstance(exc, (ValueError, InvalidPlanningDateError)):
        raise HTTPException(status_code=422, detail=str(exc))
    if isinstance(exc, AcademicCalendarError):
        raise HTTPException(status_code=400, detail=str(exc))
    raise exc


def _commit(db: Session, detail: str) -> None:
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=detail)


def _can_view_teacher(
    *,
    current_user: User,
    requested_teacher_id: UUID,
    db: Session,
) -> None:
    if requested_teacher_id == current_user.id:
        return
    if get_authorized_school_ids(current_user, db) is None:
        return
    raise HTTPException(
        status_code=403,
        detail="You are not authorized to view another para-teacher's calendar.",
    )


@router.get(
    "",
    response_model=list[CalendarDayResponse],
)
def get_calendar(
    start_date: date = Query(...),
    end_date: date = Query(...),
    para_teacher_id: UUID | None = Query(None),
    current_user: User = Depends(require_permission("calendar.view")),
    db: Session = Depends(get_db),
):
    requested_teacher_id = para_teacher_id or current_user.id
    _can_view_teacher(
        current_user=current_user,
        requested_teacher_id=requested_teacher_id,
        db=db,
    )
    try:
        active_year = AcademicCalendarService.get_active_academic_year(db)
        return AcademicCalendarService.get_calendar_view(
            db,
            academic_year_id=active_year.id,
            para_teacher_id=requested_teacher_id,
            start_date=start_date,
            end_date=end_date,
            current_datetime=datetime.now(),
        )
    except (
        AcademicCalendarError,
        ValueError,
    ) as exc:
        _raise_calendar_http_error(exc)


@router.get(
    "/active",
    response_model=list[CalendarDayResponse],
    include_in_schema=False,
)
def get_active_calendar_compatibility(
    start_date: date = Query(...),
    end_date: date = Query(...),
    para_teacher_id: UUID | None = Query(None),
    current_user: User = Depends(require_permission("calendar.view")),
    db: Session = Depends(get_db),
):
    return get_calendar(
        start_date=start_date,
        end_date=end_date,
        para_teacher_id=para_teacher_id,
        current_user=current_user,
        db=db,
    )


@router.post(
    "/holidays",
    response_model=HolidayResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_holiday(
    payload: HolidayCreate,
    _authorization_user: User = Depends(
        require_permission("calendar.manage")
    ),
    db: Session = Depends(get_db),
):
    try:
        active_year = AcademicCalendarService.get_active_academic_year(db)
        holiday = AcademicCalendarService.create_academic_holiday(
            db,
            academic_year_id=active_year.id,
            holiday_date=payload.holiday_date,
            name=payload.name,
            type=payload.type,
            description=payload.description,
        )
        _commit(db, "Unable to create academic holiday.")
        db.refresh(holiday)
        return holiday
    except HTTPException:
        raise
    except (AcademicCalendarError, ValueError) as exc:
        _raise_calendar_http_error(exc)


@router.get(
    "/holidays",
    response_model=list[HolidayResponse],
)
def list_holidays(
    active_only: bool = Query(True),
    _authorization_user: User = Depends(
        require_permission("calendar.view")
    ),
    db: Session = Depends(get_db),
):
    try:
        active_year = AcademicCalendarService.get_active_academic_year(db)
        return AcademicCalendarService.list_holidays(
            db,
            active_year.id,
            active_only=active_only,
        )
    except (AcademicCalendarError, ValueError) as exc:
        _raise_calendar_http_error(exc)


@router.patch(
    "/holidays/{holiday_id}",
    response_model=HolidayResponse,
)
def update_holiday(
    holiday_id: UUID,
    payload: HolidayUpdate,
    _authorization_user: User = Depends(
        require_permission("calendar.manage")
    ),
    db: Session = Depends(get_db),
):
    try:
        holiday = AcademicCalendarService.update_holiday(
            db,
            holiday_id,
            **payload.model_dump(exclude_unset=True),
        )
        _commit(db, "Unable to update academic holiday.")
        db.refresh(holiday)
        return holiday
    except HTTPException:
        raise
    except (AcademicCalendarError, ValueError) as exc:
        _raise_calendar_http_error(exc)


@router.delete(
    "/holidays/{holiday_id}",
    response_model=HolidayResponse,
)
def deactivate_holiday(
    holiday_id: UUID,
    _authorization_user: User = Depends(
        require_permission("calendar.manage")
    ),
    db: Session = Depends(get_db),
):
    try:
        holiday = AcademicCalendarService.deactivate_holiday(
            db,
            holiday_id,
        )
        _commit(db, "Unable to deactivate academic holiday.")
        db.refresh(holiday)
        return holiday
    except HTTPException:
        raise
    except (AcademicCalendarError, ValueError) as exc:
        _raise_calendar_http_error(exc)


@router.patch(
    "/sessions/{item_id}/reschedule",
)
def reschedule_session(
    item_id: UUID,
    payload: RescheduleRequest,
    current_user: User = Depends(
        require_permission("session_plan.update")
    ),
    db: Session = Depends(get_db),
):
    item = (
        db.query(SessionPlanItem, ClassDivision.school_id)
        .join(
            ClassDivision,
            SessionPlanItem.class_division_id == ClassDivision.id,
        )
        .filter(SessionPlanItem.id == item_id)
        .first()
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Session plan item not found.")
    plan_item, school_id = item
    require_school_access(school_id, current_user, db)
    try:
        updated = SessionPlanService().update_item(
            db,
            para_teacher_id=current_user.id,
            item_id=item_id,
            planned_date=payload.planned_date,
            planned_start_time=payload.planned_start_time,
            planned_end_time=payload.planned_end_time,
        )
        _commit(db, "Unable to reschedule session plan item.")
        db.refresh(updated)
        return updated
    except HTTPException:
        raise
    except (
        SessionPlanAccessError,
        SessionPlanItemNotFoundError,
        SessionPlanItemLockedError,
        InvalidPlanningDateError,
        ValueError,
    ) as exc:
        _raise_calendar_http_error(exc)


@router.get(
    "/compliance/{week_start_date}",
    response_model=list[PlanningComplianceResponse],
)
def get_planning_compliance(
    week_start_date: date,
    current_user: User = Depends(require_permission("calendar.view")),
    db: Session = Depends(get_db),
):
    if get_authorized_school_ids(current_user, db) is not None:
        raise HTTPException(
            status_code=403,
            detail="Only project-wide users can view planning compliance.",
        )
    try:
        return AcademicCalendarService.evaluate_planning_compliance(
            db,
            week_start_date=week_start_date,
        )
    except ValueError as exc:
        _raise_calendar_http_error(exc)
