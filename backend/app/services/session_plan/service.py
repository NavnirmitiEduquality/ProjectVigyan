from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.class_division import ClassDivision
from app.models.session_plan_content import SessionPlanContent
from app.models.session_plan_item import SessionPlanItem
from app.models.session_plan_week import SessionPlanWeek
from app.models.teaching_session import TeachingSession
from app.models.user import User, UserAssignment


MIN_WEEKLY_SESSION_ITEMS = 6
TEACHING_SESSION_STARTED_STATUS = "IN_PROGRESS"


class SessionPlanError(Exception):
    """Base exception for session-planning business errors."""


class SessionPlanWeekNotFoundError(SessionPlanError):
    """Raised when a planning week does not exist."""


class SessionPlanItemNotFoundError(SessionPlanError):
    """Raised when a planning item does not exist."""


class SessionPlanContentNotFoundError(SessionPlanError):
    """Raised when lesson-plan content does not exist."""


class SessionPlanAccessError(SessionPlanError):
    """Raised when the user cannot access the requested planning scope."""


class InvalidPlanningWeekError(SessionPlanError):
    """Raised when a planning week is invalid."""


class InvalidPlanningDateError(SessionPlanError):
    """Raised when a planned date is outside the planning week."""


class DuplicatePlanningItemError(SessionPlanError):
    """Raised when the same class/division is planned twice on one date."""


class DuplicateSequenceError(SessionPlanError):
    """Raised when a sequence number is already used in the week."""


class SessionPlanItemLockedError(SessionPlanError):
    """Raised when a plan item is edited after its session has started."""


class MinimumWeeklySessionsError(SessionPlanError):
    """Raised when a week has fewer than the required number of sessions."""


class MissingLessonPlanContentError(SessionPlanError):
    """Raised when a plan item has no lesson-plan content."""


class SessionPlanAlreadyLinkedError(SessionPlanError):
    """Raised when a plan item is already linked to a teaching session."""


class SessionPlanOperation:
    """
    Result of a session-planning mutation.

    The service never commits or rolls back the caller's transaction.
    """

    def __init__(
        self,
        *,
        week: SessionPlanWeek | None = None,
        item: SessionPlanItem | None = None,
        content: SessionPlanContent | None = None,
    ) -> None:
        self.week = week
        self.item = item
        self.content = content


class SessionPlanService:
    """
    Business service for weekly session planning.

    Transaction ownership remains with the caller.
    """

    # ------------------------------------------------------------------
    # WEEK
    # ------------------------------------------------------------------

    def get_or_create_week(
        self,
        db: Session,
        *,
        para_teacher_id: UUID,
        week_start_date: date,
        data_origin: str = "PRODUCTION",
    ) -> SessionPlanWeek:
        """
        Return the teacher's planning week, creating it if necessary.

        The supplied date must be a Monday.
        """

        self._ensure_monday(week_start_date)

        existing = (
            db.query(SessionPlanWeek)
            .filter(
                SessionPlanWeek.para_teacher_id == para_teacher_id,
                SessionPlanWeek.week_start_date == week_start_date,
            )
            .first()
        )

        if existing is not None:
            return existing

        para_teacher = self._get_user(
            db,
            para_teacher_id,
        )

        # A project/school assignment is required before planning data
        # can be created. The actual class-level scope is checked when
        # plan items are added.
        self._ensure_teacher_assignment(
            db,
            para_teacher,
            week_start_date,
        )

        week = SessionPlanWeek(
            para_teacher_id=para_teacher_id,
            week_start_date=week_start_date,
            week_end_date=week_start_date.fromordinal(
                week_start_date.toordinal() + 6
            ),
            data_origin=data_origin,
        )

        db.add(week)
        db.flush()

        return week

    def get_week(
        self,
        db: Session,
        *,
        para_teacher_id: UUID,
        week_start_date: date,
    ) -> SessionPlanWeek:
        self._ensure_monday(week_start_date)

        week = (
            db.query(SessionPlanWeek)
            .filter(
                SessionPlanWeek.para_teacher_id == para_teacher_id,
                SessionPlanWeek.week_start_date == week_start_date,
            )
            .first()
        )

        if week is None:
            raise SessionPlanWeekNotFoundError(
                "Session planning week does not exist."
            )

        return week

    def validate_week(
        self,
        db: Session,
        *,
        week: SessionPlanWeek,
    ) -> SessionPlanWeek:
        """
        Validate the weekly minimum at the explicit weekly validation point.

        No maximum is imposed.
        """

        item_count = (
            db.query(SessionPlanItem)
            .filter(
                SessionPlanItem.session_plan_week_id == week.id,
            )
            .count()
        )

        if item_count < MIN_WEEKLY_SESSION_ITEMS:
            raise MinimumWeeklySessionsError(
                f"At least {MIN_WEEKLY_SESSION_ITEMS} "
                "planned sessions are required for the week."
            )

        return week

    # ------------------------------------------------------------------
    # ITEM CREATE
    # ------------------------------------------------------------------

    def create_item(
        self,
        db: Session,
        *,
        para_teacher_id: UUID,
        session_plan_week_id: UUID,
        class_division_id: UUID,
        planned_date: date,
        sequence_no: int,
        planned_start_time: time | None = None,
        planned_end_time: time | None = None,
        data_origin: str = "PRODUCTION",
    ) -> SessionPlanItem:
        week = self._get_week_by_id(
            db,
            session_plan_week_id,
        )

        self._ensure_week_owner(
            week,
            para_teacher_id,
        )

        self._ensure_planned_date(
            week,
            planned_date,
        )

        class_division = self._get_class_division(
            db,
            class_division_id,
        )

        self._ensure_class_division_access(
            db,
            para_teacher_id,
            class_division,
            planned_date,
        )

        self._ensure_no_duplicate_class_date(
            db,
            week.id,
            class_division_id,
            planned_date,
        )

        self._ensure_sequence_available(
            db,
            week.id,
            sequence_no,
        )

        item = SessionPlanItem(
            session_plan_week_id=week.id,
            class_division_id=class_division_id,
            planned_date=planned_date,
            planned_start_time=planned_start_time,
            planned_end_time=planned_end_time,
            sequence_no=sequence_no,
            data_origin=data_origin,
        )

        db.add(item)
        db.flush()

        return item

    # ------------------------------------------------------------------
    # ITEM UPDATE
    # ------------------------------------------------------------------

    def update_item(
        self,
        db: Session,
        *,
        para_teacher_id: UUID,
        item_id: UUID,
        class_division_id: UUID | None = None,
        planned_date: date | None = None,
        sequence_no: int | None = None,
        planned_start_time: time | None = None,
        planned_end_time: time | None = None,
    ) -> SessionPlanItem:
        item = self._get_item(
            db,
            item_id,
        )

        self._ensure_item_owner(
            item,
            para_teacher_id,
        )

        self._ensure_item_editable(
            db,
            item,
        )

        week = item.session_plan_week

        new_class_division_id = (
            class_division_id
            if class_division_id is not None
            else item.class_division_id
        )

        new_planned_date = (
            planned_date
            if planned_date is not None
            else item.planned_date
        )

        self._ensure_planned_date(
            week,
            new_planned_date,
        )

        class_division = self._get_class_division(
            db,
            new_class_division_id,
        )

        self._ensure_class_division_access(
            db,
            para_teacher_id,
            class_division,
            new_planned_date,
        )

        if (
            new_class_division_id != item.class_division_id
            or new_planned_date != item.planned_date
        ):
            self._ensure_no_duplicate_class_date(
                db,
                week.id,
                new_class_division_id,
                new_planned_date,
                exclude_item_id=item.id,
            )

        if (
            sequence_no is not None
            and sequence_no != item.sequence_no
        ):
            self._ensure_sequence_available(
                db,
                week.id,
                sequence_no,
                exclude_item_id=item.id,
            )
            item.sequence_no = sequence_no

        item.class_division_id = new_class_division_id
        item.planned_date = new_planned_date

        if planned_start_time is not None or planned_end_time is not None:
            if planned_start_time is None or planned_end_time is None:
                raise ValueError(
                    "planned_start_time and planned_end_time "
                    "must be provided together."
                )

            if planned_end_time <= planned_start_time:
                raise ValueError(
                    "planned_end_time must be later than "
                    "planned_start_time."
                )

            item.planned_start_time = planned_start_time
            item.planned_end_time = planned_end_time

        db.flush()

        return item

    # ------------------------------------------------------------------
    # ITEM DELETE
    # ------------------------------------------------------------------

    def delete_item(
        self,
        db: Session,
        *,
        para_teacher_id: UUID,
        item_id: UUID,
    ) -> None:
        item = self._get_item(
            db,
            item_id,
        )

        self._ensure_item_owner(
            item,
            para_teacher_id,
        )

        self._ensure_item_editable(
            db,
            item,
        )

        if item.content is not None:
            db.delete(item.content)

        db.delete(item)
        db.flush()

    # ------------------------------------------------------------------
    # LESSON PLAN CONTENT
    # ------------------------------------------------------------------

    def set_content(
        self,
        db: Session,
        *,
        para_teacher_id: UUID,
        item_id: UUID,
        content: str,
        data_origin: str = "PRODUCTION",
    ) -> SessionPlanContent:
        item = self._get_item(
            db,
            item_id,
        )

        self._ensure_item_owner(
            item,
            para_teacher_id,
        )

        self._ensure_item_editable(
            db,
            item,
        )

        content = content.strip()

        if not content:
            raise ValueError(
                "Lesson-plan content cannot be empty."
            )

        existing = (
            db.query(SessionPlanContent)
            .filter(
                SessionPlanContent.session_plan_item_id == item.id,
            )
            .first()
        )

        if existing is None:
            existing = SessionPlanContent(
                session_plan_item_id=item.id,
                content=content,
                data_origin=data_origin,
            )
            db.add(existing)
        else:
            existing.content = content

        db.flush()

        return existing

    def get_content(
        self,
        db: Session,
        *,
        para_teacher_id: UUID,
        item_id: UUID,
    ) -> SessionPlanContent:
        item = self._get_item(
            db,
            item_id,
        )

        self._ensure_item_owner(
            item,
            para_teacher_id,
        )

        content = (
            db.query(SessionPlanContent)
            .filter(
                SessionPlanContent.session_plan_item_id == item.id,
            )
            .first()
        )

        if content is None:
            raise SessionPlanContentNotFoundError(
                "Lesson-plan content does not exist."
            )

        return content

    # ------------------------------------------------------------------
    # TEACHING SESSION READINESS
    # ------------------------------------------------------------------

    def ensure_ready_for_teaching_session(
        self,
        db: Session,
        *,
        para_teacher_id: UUID,
        item_id: UUID,
    ) -> SessionPlanItem:
        """
        Validate that a plan item is eligible to be linked to a
        TeachingSession.

        This method does not create or commit a TeachingSession.
        """

        item = self._get_item(
            db,
            item_id,
        )

        self._ensure_item_owner(
            item,
            para_teacher_id,
        )

        existing_session = (
            db.query(TeachingSession)
            .filter(
                TeachingSession.session_plan_item_id == item.id,
            )
            .first()
        )

        if existing_session is not None:
            raise SessionPlanAlreadyLinkedError(
                "This session-plan item is already linked "
                "to a teaching session."
            )

        content = (
            db.query(SessionPlanContent)
            .filter(
                SessionPlanContent.session_plan_item_id == item.id,
            )
            .first()
        )

        if content is None:
            raise MissingLessonPlanContentError(
                "Lesson-plan content is required before "
                "linking the planned session."
            )

        self.validate_week(
            db,
            week=item.session_plan_week,
        )

        return item

    def link_teaching_session(
        self,
        db: Session,
        *,
        para_teacher_id: UUID,
        item_id: UUID,
    ) -> TeachingSession:
        item = self.ensure_ready_for_teaching_session(
            db,
            para_teacher_id=para_teacher_id,
            item_id=item_id,
        )

        teaching_session = TeachingSession(
            session_plan_item_id=item.id,
            class_division_id=item.class_division_id,
            para_teacher_id=para_teacher_id,
            session_date=item.planned_date,
            planned_start_time=item.planned_start_time,
            planned_end_time=item.planned_end_time,
            status="PLANNED",
            data_origin="PRODUCTION",
        )

        db.add(teaching_session)
        db.flush()

        return teaching_session

    # ------------------------------------------------------------------
    # INTERNAL LOOKUPS
    # ------------------------------------------------------------------

    @staticmethod
    def _get_user(
        db: Session,
        user_id: UUID,
    ) -> User:
        user = (
            db.query(User)
            .filter(User.id == user_id)
            .first()
        )

        if user is None:
            raise SessionPlanAccessError(
                "Para-teacher does not exist."
            )

        return user

    @staticmethod
    def _get_week_by_id(
        db: Session,
        week_id: UUID,
    ) -> SessionPlanWeek:
        week = (
            db.query(SessionPlanWeek)
            .filter(SessionPlanWeek.id == week_id)
            .first()
        )

        if week is None:
            raise SessionPlanWeekNotFoundError(
                "Session planning week does not exist."
            )

        return week

    @staticmethod
    def _get_item(
        db: Session,
        item_id: UUID,
    ) -> SessionPlanItem:
        item = (
            db.query(SessionPlanItem)
            .filter(SessionPlanItem.id == item_id)
            .first()
        )

        if item is None:
            raise SessionPlanItemNotFoundError(
                "Session planning item does not exist."
            )

        return item

    @staticmethod
    def _get_class_division(
        db: Session,
        class_division_id: UUID,
    ) -> ClassDivision:
        class_division = (
            db.query(ClassDivision)
            .filter(
                ClassDivision.id == class_division_id,
            )
            .first()
        )

        if class_division is None:
            raise SessionPlanAccessError(
                "Class/division does not exist."
            )

        return class_division

    # ------------------------------------------------------------------
    # INTERNAL AUTHORIZATION
    # ------------------------------------------------------------------

    @staticmethod
    def _ensure_week_owner(
        week: SessionPlanWeek,
        para_teacher_id: UUID,
    ) -> None:
        if week.para_teacher_id != para_teacher_id:
            raise SessionPlanAccessError(
                "You cannot modify another para-teacher's plan."
            )

    @staticmethod
    def _ensure_item_owner(
        item: SessionPlanItem,
        para_teacher_id: UUID,
    ) -> None:
        if item.session_plan_week.para_teacher_id != para_teacher_id:
            raise SessionPlanAccessError(
                "You cannot modify another para-teacher's plan."
            )

    def _ensure_teacher_assignment(
        self,
        db: Session,
        para_teacher: User,
        target_date: date,
    ) -> None:
        assignment = (
            db.query(UserAssignment)
            .filter(
                UserAssignment.user_id == para_teacher.id,
                UserAssignment.is_active.is_(True),
                UserAssignment.start_date <= target_date,
                (
                    UserAssignment.end_date.is_(None)
                    | (UserAssignment.end_date >= target_date)
                ),
            )
            .first()
        )

        if assignment is None:
            raise SessionPlanAccessError(
                "Para-teacher is not assigned to an active "
                "planning scope for this date."
            )

    def _ensure_class_division_access(
        self,
        db: Session,
        para_teacher_id: UUID,
        class_division: ClassDivision,
        target_date: date,
    ) -> None:
        assignment_query = (
            db.query(UserAssignment)
            .filter(
                UserAssignment.user_id == para_teacher_id,
                UserAssignment.is_active.is_(True),
                UserAssignment.start_date <= target_date,
                (
                    UserAssignment.end_date.is_(None)
                    | (UserAssignment.end_date >= target_date)
                ),
            )
        )

        assignments = assignment_query.all()

        for assignment in assignments:
            if assignment.scope_type == "PROJECT":
                return

            if (
                assignment.scope_type == "SCHOOL"
                and assignment.school_id == class_division.school_id
            ):
                return

        raise SessionPlanAccessError(
            "Para-teacher is not authorized for this class/division."
        )

    # ------------------------------------------------------------------
    # INTERNAL VALIDATION
    # ------------------------------------------------------------------

    @staticmethod
    def _ensure_monday(
        week_start_date: date,
    ) -> None:
        if week_start_date.isoweekday() != 1:
            raise InvalidPlanningWeekError(
                "Session planning weeks must start on Monday."
            )

    @staticmethod
    def _ensure_planned_date(
        week: SessionPlanWeek,
        planned_date: date,
    ) -> None:
        if not (
            week.week_start_date
            <= planned_date
            <= week.week_end_date
        ):
            raise InvalidPlanningDateError(
                "Planned date must fall within the planning week."
            )

    @staticmethod
    def _ensure_no_duplicate_class_date(
        db: Session,
        week_id: UUID,
        class_division_id: UUID,
        planned_date: date,
        *,
        exclude_item_id: UUID | None = None,
    ) -> None:
        query = (
            db.query(SessionPlanItem)
            .filter(
                SessionPlanItem.session_plan_week_id == week_id,
                SessionPlanItem.class_division_id == class_division_id,
                SessionPlanItem.planned_date == planned_date,
            )
        )

        if exclude_item_id is not None:
            query = query.filter(
                SessionPlanItem.id != exclude_item_id,
            )

        if query.first() is not None:
            raise DuplicatePlanningItemError(
                "The same class/division cannot be planned "
                "more than once on the same date."
            )

    @staticmethod
    def _ensure_sequence_available(
        db: Session,
        week_id: UUID,
        sequence_no: int,
        *,
        exclude_item_id: UUID | None = None,
    ) -> None:
        if sequence_no <= 0:
            raise ValueError(
                "sequence_no must be greater than zero."
            )

        query = (
            db.query(SessionPlanItem)
            .filter(
                SessionPlanItem.session_plan_week_id == week_id,
                SessionPlanItem.sequence_no == sequence_no,
            )
        )

        if exclude_item_id is not None:
            query = query.filter(
                SessionPlanItem.id != exclude_item_id,
            )

        if query.first() is not None:
            raise DuplicateSequenceError(
                "The sequence number is already used in this week."
            )

    @staticmethod
    def _ensure_item_editable(
        db: Session,
        item: SessionPlanItem,
    ) -> None:
        teaching_session = (
            db.query(TeachingSession)
            .filter(
                TeachingSession.session_plan_item_id == item.id,
            )
            .first()
        )

        if teaching_session is None:
            return

        if teaching_session.status == TEACHING_SESSION_STARTED_STATUS:
            raise SessionPlanItemLockedError(
                "The session-plan item cannot be edited because "
                "the teaching session has started."
            )

        # A completed/cancelled session is also no longer a normal
        # planning-edit state. The explicit confirmed requirement is
        # that edits stop once the session has started.
        if teaching_session.status in {
            "COMPLETED",
            "CANCELLED",
        }:
            raise SessionPlanItemLockedError(
                "The session-plan item is no longer editable "
                "through the normal planning workflow."
            )