from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from uuid import UUID

from sqlalchemy.orm import Session

from app.models import (
    AcademicHoliday,
    AcademicYear,
    SessionPlanItem,
    SessionPlanWeek,
    TeachingSession,
)


class AcademicCalendarError(Exception):
    """Base exception for academic-calendar business errors."""


class AcademicYearNotFoundError(AcademicCalendarError):
    """Raised when an academic year cannot be found."""


class ActiveAcademicYearNotFoundError(AcademicCalendarError):
    """Raised when no active academic year exists."""


class AcademicHolidayNotFoundError(AcademicCalendarError):
    """Raised when an academic holiday cannot be found."""


class AcademicYearAlreadyExistsError(AcademicCalendarError):
    """Raised when an academic-year name already exists."""


class AcademicHolidayAlreadyExistsError(AcademicCalendarError):
    """Raised when a holiday date already exists for an academic year."""


@dataclass(frozen=True)
class CalendarSessionDTO:
    session_plan_item_id: UUID
    para_teacher_id: UUID
    class_division_id: UUID
    planned_start_time: time | None
    planned_end_time: time | None
    sequence_no: int
    teaching_session_id: UUID | None
    teaching_session_status: str | None
    derived_status: str


@dataclass(frozen=True)
class CalendarDayDTO:
    calendar_date: date
    is_working_day: bool
    is_holiday: bool
    holiday_name: str | None
    holiday_type: str | None
    sessions: list[CalendarSessionDTO]


@dataclass(frozen=True)
class PlanningComplianceDTO:
    para_teacher_id: UUID
    week_start_date: date
    planned_session_count: int
    minimum_required: int
    minimum_met: bool


class AcademicCalendarService:
    MINIMUM_WEEKLY_SESSIONS = 6

    @staticmethod
    def get_active_academic_year(db: Session) -> AcademicYear:
        academic_year = (
            db.query(AcademicYear)
            .filter(AcademicYear.is_active.is_(True))
            .order_by(AcademicYear.start_date.desc())
            .first()
        )
        if academic_year is None:
            raise ActiveAcademicYearNotFoundError(
                "No active academic year exists."
            )
        return academic_year

    @staticmethod
    def get_academic_year(
        db: Session,
        academic_year_id: UUID,
    ) -> AcademicYear:
        academic_year = (
            db.query(AcademicYear)
            .filter(AcademicYear.id == academic_year_id)
            .first()
        )
        if academic_year is None:
            raise AcademicYearNotFoundError(
                f"Academic year not found: {academic_year_id}"
            )
        return academic_year

    @staticmethod
    def create_academic_year(
        db: Session,
        *,
        name: str,
        start_date: date,
        end_date: date,
        is_active: bool = True,
        data_origin: str = "PRODUCTION",
    ) -> AcademicYear:
        if start_date >= end_date:
            raise ValueError("start_date must be before end_date.")

        existing = (
            db.query(AcademicYear)
            .filter(AcademicYear.name == name)
            .first()
        )
        if existing is not None:
            raise AcademicYearAlreadyExistsError(
                f"Academic year already exists: {name}"
            )

        academic_year = AcademicYear(
            name=name,
            start_date=start_date,
            end_date=end_date,
            is_active=is_active,
            data_origin=data_origin,
        )
        db.add(academic_year)
        db.flush()
        return academic_year

    @staticmethod
    def create_academic_holiday(
        db: Session,
        *,
        academic_year_id: UUID,
        holiday_date: date,
        name: str,
        type: str,
        description: str | None = None,
        is_active: bool = True,
        data_origin: str = "PRODUCTION",
    ) -> AcademicHoliday:
        year = AcademicCalendarService.get_academic_year(
            db,
            academic_year_id,
        )
        if not year.start_date <= holiday_date <= year.end_date:
            raise ValueError(
                "Holiday date must fall within the academic year."
            )

        existing = (
            db.query(AcademicHoliday)
            .filter(
                AcademicHoliday.academic_year_id == academic_year_id,
                AcademicHoliday.holiday_date == holiday_date,
            )
            .first()
        )
        if existing is not None:
            raise AcademicHolidayAlreadyExistsError(
                "Holiday already exists for this academic year and date."
            )

        holiday = AcademicHoliday(
            academic_year_id=academic_year_id,
            holiday_date=holiday_date,
            name=name,
            type=type,
            description=description,
            is_active=is_active,
            data_origin=data_origin,
        )
        db.add(holiday)
        db.flush()
        return holiday

    @staticmethod
    def list_holidays(
        db: Session,
        academic_year_id: UUID,
        *,
        active_only: bool = True,
    ) -> list[AcademicHoliday]:
        AcademicCalendarService.get_academic_year(db, academic_year_id)
        query = db.query(AcademicHoliday).filter(
            AcademicHoliday.academic_year_id == academic_year_id
        )
        if active_only:
            query = query.filter(AcademicHoliday.is_active.is_(True))
        return query.order_by(
            AcademicHoliday.holiday_date.asc(),
            AcademicHoliday.name.asc(),
        ).all()

    @staticmethod
    def get_holiday(db: Session, holiday_id: UUID) -> AcademicHoliday:
        holiday = (
            db.query(AcademicHoliday)
            .filter(AcademicHoliday.id == holiday_id)
            .first()
        )
        if holiday is None:
            raise AcademicHolidayNotFoundError(
                f"Academic holiday not found: {holiday_id}"
            )
        return holiday

    @staticmethod
    def update_holiday(
        db: Session,
        holiday_id: UUID,
        *,
        holiday_date: date | None = None,
        name: str | None = None,
        type: str | None = None,
        description: str | None = None,
        is_active: bool | None = None,
    ) -> AcademicHoliday:
        holiday = AcademicCalendarService.get_holiday(db, holiday_id)
        academic_year = AcademicCalendarService.get_academic_year(
            db,
            holiday.academic_year_id,
        )
        new_date = holiday_date or holiday.holiday_date
        if not academic_year.start_date <= new_date <= academic_year.end_date:
            raise ValueError(
                "Holiday date must fall within the academic year."
            )

        if new_date != holiday.holiday_date:
            duplicate = (
                db.query(AcademicHoliday)
                .filter(
                    AcademicHoliday.academic_year_id
                    == holiday.academic_year_id,
                    AcademicHoliday.holiday_date == new_date,
                    AcademicHoliday.id != holiday.id,
                )
                .first()
            )
            if duplicate is not None:
                raise AcademicHolidayAlreadyExistsError(
                    "Holiday already exists for this academic year and date."
                )

        holiday.holiday_date = new_date
        if name is not None:
            holiday.name = name
        if type is not None:
            holiday.type = type
        if description is not None:
            holiday.description = description
        if is_active is not None:
            holiday.is_active = is_active
        db.flush()
        return holiday

    @staticmethod
    def deactivate_holiday(
        db: Session,
        holiday_id: UUID,
    ) -> AcademicHoliday:
        return AcademicCalendarService.update_holiday(
            db,
            holiday_id,
            is_active=False,
        )

    @staticmethod
    def get_calendar_view(
        db: Session,
        *,
        academic_year_id: UUID,
        para_teacher_id: UUID | None,
        start_date: date,
        end_date: date,
        current_date: date | None = None,
        current_datetime: datetime | None = None,
    ) -> list[CalendarDayDTO]:
        if start_date > end_date:
            raise ValueError("start_date must not be after end_date.")

        academic_year = AcademicCalendarService.get_academic_year(
            db,
            academic_year_id,
        )
        if (
            start_date < academic_year.start_date
            or end_date > academic_year.end_date
        ):
            raise ValueError(
                "Calendar range must fall within the academic year."
            )

        today = current_date or date.today()
        now = current_datetime
        holidays = (
            db.query(AcademicHoliday)
            .filter(
                AcademicHoliday.academic_year_id == academic_year_id,
                AcademicHoliday.holiday_date >= start_date,
                AcademicHoliday.holiday_date <= end_date,
                AcademicHoliday.is_active.is_(True),
            )
            .all()
        )
        holiday_map = {holiday.holiday_date: holiday for holiday in holidays}

        query = (
            db.query(SessionPlanItem, SessionPlanWeek, TeachingSession)
            .join(
                SessionPlanWeek,
                SessionPlanItem.session_plan_week_id == SessionPlanWeek.id,
            )
            .outerjoin(
                TeachingSession,
                SessionPlanItem.id == TeachingSession.session_plan_item_id,
            )
            .filter(
                SessionPlanItem.planned_date >= start_date,
                SessionPlanItem.planned_date <= end_date,
                SessionPlanWeek.week_start_date
                <= SessionPlanItem.planned_date,
                SessionPlanWeek.week_end_date
                >= SessionPlanItem.planned_date,
            )
        )
        if para_teacher_id is not None:
            query = query.filter(
                SessionPlanWeek.para_teacher_id == para_teacher_id
            )

        items_by_date: dict[
            date, list[tuple[SessionPlanItem, SessionPlanWeek, TeachingSession | None]]
        ] = {}
        for item, week, teaching_session in query.all():
            items_by_date.setdefault(item.planned_date, []).append(
                (item, week, teaching_session)
            )

        days: list[CalendarDayDTO] = []
        calendar_date = start_date
        while calendar_date <= end_date:
            holiday = holiday_map.get(calendar_date)
            sessions = [
                AcademicCalendarService._session_dto(
                    item=item,
                    week=week,
                    teaching_session=teaching_session,
                    holiday=holiday is not None,
                    today=today,
                    now=now,
                )
                for item, week, teaching_session in items_by_date.get(
                    calendar_date, []
                )
            ]
            sessions.sort(
                key=lambda session: (
                    session.planned_start_time or time.min,
                    session.sequence_no,
                )
            )
            days.append(
                CalendarDayDTO(
                    calendar_date=calendar_date,
                    is_working_day=calendar_date.weekday() < 5
                    and holiday is None,
                    is_holiday=holiday is not None,
                    holiday_name=holiday.name if holiday else None,
                    holiday_type=holiday.type if holiday else None,
                    sessions=sessions,
                )
            )
            calendar_date += timedelta(days=1)
        return days

    @staticmethod
    def _session_dto(
        *,
        item: SessionPlanItem,
        week: SessionPlanWeek,
        teaching_session: TeachingSession | None,
        holiday: bool,
        today: date,
        now: datetime | None,
    ) -> CalendarSessionDTO:
        status = teaching_session.status if teaching_session else None
        if status == "COMPLETED":
            derived_status = "COMPLETED"
        elif holiday or status == "CANCELLED":
            derived_status = "RESCHEDULE_REQUIRED"
        elif item.planned_date < today:
            derived_status = "RESCHEDULE_REQUIRED"
        elif (
            item.planned_date == today
            and now is not None
            and item.planned_end_time is not None
            and now.time() > item.planned_end_time
            and status != "COMPLETED"
        ):
            derived_status = "RESCHEDULE_REQUIRED"
        else:
            derived_status = "PLANNED"

        return CalendarSessionDTO(
            session_plan_item_id=item.id,
            para_teacher_id=week.para_teacher_id,
            class_division_id=item.class_division_id,
            planned_start_time=item.planned_start_time,
            planned_end_time=item.planned_end_time,
            sequence_no=item.sequence_no,
            teaching_session_id=(
                teaching_session.id if teaching_session else None
            ),
            teaching_session_status=status,
            derived_status=derived_status,
        )

    @staticmethod
    def evaluate_planning_compliance(
        db: Session,
        *,
        week_start_date: date,
    ) -> list[PlanningComplianceDTO]:
        if week_start_date.weekday() != 0:
            raise ValueError("week_start_date must be a Monday.")

        weeks = (
            db.query(SessionPlanWeek)
            .filter(SessionPlanWeek.week_start_date == week_start_date)
            .all()
        )
        counts = {
            week.id: db.query(SessionPlanItem)
            .filter(SessionPlanItem.session_plan_week_id == week.id)
            .count()
            for week in weeks
        }
        return [
            PlanningComplianceDTO(
                para_teacher_id=week.para_teacher_id,
                week_start_date=week_start_date,
                planned_session_count=counts[week.id],
                minimum_required=AcademicCalendarService.MINIMUM_WEEKLY_SESSIONS,
                minimum_met=counts[week.id]
                >= AcademicCalendarService.MINIMUM_WEEKLY_SESSIONS,
            )
            for week in weeks
        ]
