from datetime import date
from uuid import uuid4

import pytest

from app.database import SessionLocal
from app.models import (
    ClassDivision,
    PlanningNotification,
    Role,
    School,
    SessionPlanWeek,
    User,
    UserAssignment,
    UserRole,
)
from app.services.planning_notification_service import (
    PlanningNotificationService,
)
from scripts.run_weekly_planning_compliance import run_compliance_job


EXECUTION_DATE = date(2026, 11, 21)
TARGET_WEEK_START = date(2026, 11, 23)


def test_real_job_persists_notifications_without_duplicates():
    db = SessionLocal()
    suffix = uuid4().hex[:12]

    school = None
    division = None
    teacher = None
    recipients = []
    week = None

    try:
        # Create uniquely owned fixture records.
        school = School(
            school_code=f"IT-{suffix}",
            school_name=f"Integration Test School {suffix}",
            status="ACTIVE",
            data_origin="PRODUCTION",
        )
        db.add(school)
        db.flush()

        division = ClassDivision(
            school_id=school.id,
            class_level=5,
            division="A",
            status="ACTIVE",
            data_origin="TEST",
        )
        db.add(division)

        teacher = User(
            user_code=f"IT-T-{suffix}",
            account_category="PARA_TEACHER",
            full_name="Compliance Integration Teacher",
            email=f"it-teacher-{suffix}@example.com",
            password_hash="test-only-not-a-real-password",
            status="ACTIVE",
            data_origin="PRODUCTION",
        )
        db.add(teacher)

        for role_code in ("MANAGEMENT", "STEM_COORDINATOR"):
            recipient = User(
                user_code=f"IT-{role_code[:2]}-{suffix}",
                account_category=role_code,
                full_name=f"Compliance Integration {role_code}",
                email=f"it-{role_code.lower()}-{suffix}@example.com",
                password_hash="test-only-not-a-real-password",
                status="ACTIVE",
                data_origin="PRODUCTION",
            )
            db.add(recipient)
            recipients.append((recipient, role_code))

        db.flush()

        teacher_role = (
            db.query(Role).filter(Role.code == "PARA_TEACHER").one()
        )
        db.add(
            UserRole(
                user_id=teacher.id,
                role_id=teacher_role.id,
                is_active=True,
            )
        )
        db.add(
            UserAssignment(
                user_id=teacher.id,
                scope_type="SCHOOL",
                school_id=school.id,
                start_date=date(2026, 1, 1),
                is_active=True,
            )
        )

        for recipient, role_code in recipients:
            role = db.query(Role).filter(Role.code == role_code).one()
            db.add(
                UserRole(
                    user_id=recipient.id,
                    role_id=role.id,
                    is_active=True,
                )
            )

        week = SessionPlanWeek(
            para_teacher_id=teacher.id,
            week_start_date=TARGET_WEEK_START,
            week_end_date=date(2026, 11, 29),
            data_origin="TEST",
        )
        db.add(week)
        db.commit()

        # Safety guards: the job must have no unrelated teacher or
        # pre-existing weekly notification to process for this week.
        eligible_teacher_ids = (
            PlanningNotificationService._eligible_para_teacher_ids(
                db,
                week_start_date=TARGET_WEEK_START,
            )
        )
        assert eligible_teacher_ids == {teacher.id}, (
            "Safety stop: vigyan_test contains other eligible Para Teachers "
            "for the target week. The real job was not executed."
        )

        existing_notifications = (
            db.query(PlanningNotification)
            .filter(
                PlanningNotification.week_start_date == TARGET_WEEK_START,
                PlanningNotification.notification_type
                == PlanningNotificationService.WEEKLY_NONCOMPLIANCE,
            )
            .count()
        )
        assert existing_notifications == 0, (
            "Safety stop: weekly notifications already exist for the "
            "target week. The real job was not executed."
        )

        # First real execution: the fixture has zero planned items.
        first_run_count = run_compliance_job(
            db,
            execution_date=EXECUTION_DATE,
            dry_run=False,
        )
        assert first_run_count >= len(recipients)

        first_notifications = (
            db.query(PlanningNotification)
            .filter(
                PlanningNotification.para_teacher_id == teacher.id,
                PlanningNotification.week_start_date == TARGET_WEEK_START,
                PlanningNotification.notification_type
                == PlanningNotificationService.WEEKLY_NONCOMPLIANCE,
            )
            .all()
        )

        first_ids = {notification.id for notification in first_notifications}
        first_recipient_ids = {
            notification.recipient_id for notification in first_notifications
        }

        expected_fixture_recipient_ids = {
            recipient.id for recipient, _ in recipients
        }

        assert expected_fixture_recipient_ids.issubset(first_recipient_ids)
        assert len(first_ids) == len(first_notifications)
        assert all(not item.is_read for item in first_notifications)

        # Second real execution: it must reuse the committed records.
        second_run_count = run_compliance_job(
            db,
            execution_date=EXECUTION_DATE,
            dry_run=False,
        )

        second_notifications = (
            db.query(PlanningNotification)
            .filter(
                PlanningNotification.para_teacher_id == teacher.id,
                PlanningNotification.week_start_date == TARGET_WEEK_START,
                PlanningNotification.notification_type
                == PlanningNotificationService.WEEKLY_NONCOMPLIANCE,
            )
            .all()
        )

        second_ids = {
            notification.id for notification in second_notifications
        }

        assert second_run_count == len(first_ids)
        assert len(second_notifications) == len(first_notifications)
        assert second_ids == first_ids

    finally:
        # The job commits, so cleanup must be a separate transaction.
        db.rollback()

        if teacher is not None:
            db.query(PlanningNotification).filter(
                PlanningNotification.para_teacher_id == teacher.id
            ).delete(synchronize_session=False)

            if week is not None:
                db.query(SessionPlanWeek).filter(
                    SessionPlanWeek.id == week.id
                ).delete(synchronize_session=False)

            db.query(UserAssignment).filter(
                UserAssignment.user_id == teacher.id
            ).delete(synchronize_session=False)

            db.query(UserRole).filter(
                UserRole.user_id == teacher.id
            ).delete(synchronize_session=False)

        recipient_ids = [
            recipient.id for recipient, _ in recipients
        ]
        if recipient_ids:
            db.query(PlanningNotification).filter(
                PlanningNotification.recipient_id.in_(recipient_ids)
            ).delete(synchronize_session=False)

            db.query(UserRole).filter(
                UserRole.user_id.in_(recipient_ids)
            ).delete(synchronize_session=False)

            db.query(User).filter(
                User.id.in_(recipient_ids)
            ).delete(synchronize_session=False)

        if teacher is not None:
            db.query(User).filter(
                User.id == teacher.id
            ).delete(synchronize_session=False)

        if division is not None:
            db.query(ClassDivision).filter(
                ClassDivision.id == division.id
            ).delete(synchronize_session=False)

        if school is not None:
            db.query(School).filter(
                School.id == school.id
            ).delete(synchronize_session=False)

        db.commit()
        db.close()