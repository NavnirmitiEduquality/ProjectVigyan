from datetime import date, datetime
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import (
    AcademicHoliday,
    AcademicYear,
    PlanningNotification,
    Role,
    School,
    SessionPlanItem,
    SessionPlanWeek,
    TeachingSession,
    User,
    UserAssignment,
    UserRole,
)
from app.services.academic_calendar.service import AcademicCalendarService


class PlanningNotificationService:
    """Generate planning notifications without owning the transaction."""

    WEEKLY_NONCOMPLIANCE = "WEEKLY_PLANNING_NONCOMPLIANCE"
    RESCHEDULE_REQUIRED = "SESSION_RESCHEDULE_REQUIRED"
    MANAGEMENT_ROLES = {"MANAGEMENT", "STEM_COORDINATOR"}

    @staticmethod
    def _active_management_recipient_ids(db: Session) -> set[UUID]:
        rows = (
            db.query(User.id)
            .join(UserRole, UserRole.user_id == User.id)
            .join(Role, Role.id == UserRole.role_id)
            .filter(
                User.status == "ACTIVE",
                UserRole.is_active.is_(True),
                Role.code.in_(
                    PlanningNotificationService.MANAGEMENT_ROLES
                ),
            )
            .distinct()
            .all()
        )
        return {user_id for (user_id,) in rows}

    @staticmethod
    def _eligible_para_teacher_ids(
        db: Session,
        *,
        week_start_date: date,
    ) -> set[UUID]:
        """Return active Para Teachers with an effective active school assignment."""
        week_end_date = date.fromordinal(week_start_date.toordinal() + 6)

        rows = (
            db.query(User.id)
            .join(UserRole, UserRole.user_id == User.id)
            .join(Role, Role.id == UserRole.role_id)
            .join(UserAssignment, UserAssignment.user_id == User.id)
            .join(School, School.id == UserAssignment.school_id)
            .filter(
                User.status == "ACTIVE",
                UserRole.is_active.is_(True),
                Role.code == "PARA_TEACHER",
                UserAssignment.scope_type == "SCHOOL",
                UserAssignment.is_active.is_(True),
                UserAssignment.start_date <= week_end_date,
                (
                    (UserAssignment.end_date.is_(None))
                    | (UserAssignment.end_date >= week_start_date)
                ),
                School.status == "ACTIVE",
            )
            .distinct()
            .all()
        )
        return {user_id for (user_id,) in rows}

    @staticmethod
    def _upsert_notification(
        db: Session,
        *,
        recipient_id: UUID,
        notification_type: str,
        para_teacher_id: UUID,
        message: str,
        session_plan_item_id: UUID | None = None,
        week_start_date: date | None = None,
    ) -> PlanningNotification:
        query = db.query(PlanningNotification).filter(
            PlanningNotification.recipient_id == recipient_id,
            PlanningNotification.notification_type == notification_type,
        )

        if notification_type == PlanningNotificationService.WEEKLY_NONCOMPLIANCE:
            query = query.filter(
                PlanningNotification.para_teacher_id == para_teacher_id,
                PlanningNotification.week_start_date == week_start_date,
            )
        elif notification_type == PlanningNotificationService.RESCHEDULE_REQUIRED:
            query = query.filter(
                PlanningNotification.session_plan_item_id
                == session_plan_item_id
            )
        else:
            raise ValueError(
                f"Unsupported planning notification type: {notification_type}"
            )

        notification = query.first()
        if notification is None:
            notification = PlanningNotification(
                recipient_id=recipient_id,
                notification_type=notification_type,
                para_teacher_id=para_teacher_id,
                session_plan_item_id=session_plan_item_id,
                week_start_date=week_start_date,
                message=message,
                is_read=False,
            )
            db.add(notification)
        else:
            notification.message = message
            notification.is_read = False

        # Flush to surface constraint failures; transaction ownership stays
        # with the caller. The unique indexes protect against concurrent inserts.
        db.flush()
        return notification


    def generate_weekly_noncompliance(
        self,
        db: Session,
        *,
        week_start_date: date,
    ) -> list[PlanningNotification]:
        """Notify management of shortfalls and clear alerts when corrected."""
        if week_start_date.weekday() != 0:
            raise ValueError("week_start_date must be a Monday.")

        teacher_ids = self._eligible_para_teacher_ids(
            db,
            week_start_date=week_start_date,
        )
        recipients = self._active_management_recipient_ids(db)

        # Reconcile notifications for teachers who are no longer eligible
        # before processing the teachers who remain eligible.
        existing_weekly_notifications = (
            db.query(PlanningNotification)
            .filter(
                PlanningNotification.week_start_date == week_start_date,
                PlanningNotification.notification_type
                == self.WEEKLY_NONCOMPLIANCE,
            )
            .all()
        )
        notifications_by_teacher: dict[UUID, list[PlanningNotification]] = {}
        created_or_updated: list[PlanningNotification] = []

        for notification in existing_weekly_notifications:
            notifications_by_teacher.setdefault(
                notification.para_teacher_id, []
            ).append(notification)

            if (
                notification.para_teacher_id not in teacher_ids
                and not notification.is_read
            ):
                notification.is_read = True
                created_or_updated.append(notification)

        if not teacher_ids:
            db.flush()
            return created_or_updated

        weeks = (
            db.query(SessionPlanWeek)
            .filter(
                SessionPlanWeek.week_start_date == week_start_date,
                SessionPlanWeek.para_teacher_id.in_(teacher_ids),
            )
            .all()
        )
        week_by_teacher = {
            week.para_teacher_id: week
            for week in weeks
        }

        minimum_required = AcademicCalendarService.MINIMUM_WEEKLY_SESSIONS

        for teacher_id in teacher_ids:
            week = week_by_teacher.get(teacher_id)
            planned_count = (
                db.query(func.count(SessionPlanItem.id))
                .filter(
                    SessionPlanItem.session_plan_week_id == week.id
                )
                .scalar()
                or 0
                if week is not None
                else 0
            )


            existing_notifications = notifications_by_teacher.get(
                teacher_id, []
            )

            for notification in existing_notifications:
                if (
                    notification.recipient_id not in recipients
                    and not notification.is_read
                ):
                    notification.is_read = True
                    created_or_updated.append(notification)


            if planned_count >= minimum_required:
                # Preserve the notification record, but stop presenting the
                # former shortfall as unread/current.
                for notification in existing_notifications:
                    if not notification.is_read:
                        notification.is_read = True
                        created_or_updated.append(notification)
                continue

            message = (
                f"Para Teacher {teacher_id} has {planned_count} planned "
                f"sessions for the week starting {week_start_date}; at least "
                f"{minimum_required} are required."
            )

            for recipient_id in recipients:
                created_or_updated.append(
                    self._upsert_notification(
                        db,
                        recipient_id=recipient_id,
                        notification_type=self.WEEKLY_NONCOMPLIANCE,
                        para_teacher_id=teacher_id,
                        week_start_date=week_start_date,
                        message=message,
                    )
                )

        db.flush()

        # Reconciliation can encounter the same notification through
        # multiple resolution conditions. Return each changed record once.
        unique_notifications = {
            notification.id: notification
            for notification in created_or_updated
        }
        return list(unique_notifications.values())

    @staticmethod
    def _is_active_holiday(
        db: Session,
        *,
        planned_date: date,
    ) -> bool:
        return (
            db.query(AcademicHoliday.id)
            .join(
                AcademicYear,
                AcademicYear.id == AcademicHoliday.academic_year_id,
            )
            .filter(
                AcademicHoliday.holiday_date == planned_date,
                AcademicHoliday.is_active.is_(True),
                AcademicYear.is_active.is_(True),
                AcademicYear.start_date <= planned_date,
                AcademicYear.end_date >= planned_date,
            )
            .first()
            is not None
        )

    def generate_reschedule_required(
        self,
        db: Session,
        *,
        session_plan_item_id: UUID,
        current_date: date | None = None,
        current_datetime: datetime | None = None,
    ) -> PlanningNotification | None:
        """Notify the owning active Para Teacher if an item needs rescheduling."""
        item = db.get(SessionPlanItem, session_plan_item_id)
        if item is None:
            return None

        week = db.get(SessionPlanWeek, item.session_plan_week_id)
        if week is None:
            return None

        existing_notifications = (
            db.query(PlanningNotification)
            .filter(
                PlanningNotification.session_plan_item_id == item.id,
                PlanningNotification.notification_type
                == self.RESCHEDULE_REQUIRED,
            )
            .all()
        )
        teaching_session = (
            db.query(TeachingSession)
            .filter(
                TeachingSession.session_plan_item_id == item.id
            )
            .first()
        )

        today = current_date or date.today()
        now = current_datetime

        completed = (
            teaching_session is not None
            and teaching_session.status == "COMPLETED"
        )
        holiday = self._is_active_holiday(
            db,
            planned_date=item.planned_date,
        )

        needs_reschedule = not completed and (
            holiday
            or (
                teaching_session is not None
                and teaching_session.status == "CANCELLED"
            )
            or item.planned_date < today
            or (
                item.planned_date == today
                and now is not None
                and item.planned_end_time is not None
                and now.time() > item.planned_end_time
            )
        )

        if not needs_reschedule:
            for notification in existing_notifications:
                if not notification.is_read:
                    notification.is_read = True
            db.flush()
            return None

        teacher = db.get(User, week.para_teacher_id)
        if teacher is None or teacher.status != "ACTIVE":
            for notification in existing_notifications:
                if not notification.is_read:
                    notification.is_read = True
            db.flush()
            return None

        return self._upsert_notification(
            db,
            recipient_id=teacher.id,
            notification_type=self.RESCHEDULE_REQUIRED,
            para_teacher_id=teacher.id,
            session_plan_item_id=item.id,
            message=(
                f"Planned session {item.id} requires rescheduling. "
                f"Review the planned date {item.planned_date}."
            ),
        )
