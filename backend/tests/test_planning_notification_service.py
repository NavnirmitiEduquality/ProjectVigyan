from datetime import date
from uuid import uuid4

import pytest

from app.database import SessionLocal
from app.models import (
    ClassDivision,
    PlanningNotification,
    Role,
    School,
    SessionPlanItem,
    SessionPlanWeek,
    User,
    UserAssignment,
    UserRole,
    TeachingSession,
    AcademicHoliday,
    AcademicYear,
)
from app.services.academic_calendar.service import AcademicCalendarService
from app.services.planning_notification_service import PlanningNotificationService


@pytest.fixture
def planning_notification_fixture():
    db = SessionLocal()
    suffix = uuid4().hex[:10]
    week_start = date(2026, 10, 19)  # Monday

    school = None
    division = None
    teacher = None
    recipients = []
    extra_teachers = []
    week = None

    try:
        school = School(
            school_code=f"PN-{suffix}",
            school_name=f"Planning Notification School {suffix}",
            status="ACTIVE",
            data_origin="TEST",
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
            user_code=f"PN-T-{suffix}",
            full_name="Planning Test Teacher",
            email=f"pn-teacher-{suffix}@example.com",
            password_hash="test-only-not-a-real-password",
            status="ACTIVE",
            data_origin="TEST",
        )
        db.add(teacher)

        for role_code, label in (
            ("MANAGEMENT", "Management"),
            ("STEM_COORDINATOR", "STEM Coordinator"),
        ):
            recipient = User(
                user_code=f"PN-{label[:2].upper()}-{suffix}",
                full_name=f"Planning Test {label}",
                email=f"pn-{label.lower().replace(' ', '-')}-{suffix}@example.com",
                password_hash="test-only-not-a-real-password",
                status="ACTIVE",
                data_origin="TEST",
            )
            db.add(recipient)
            recipients.append((recipient, role_code))

        db.flush()

        teacher_role = db.query(Role).filter(Role.code == "PARA_TEACHER").one()
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

        db.flush()

        week = SessionPlanWeek(
            para_teacher_id=teacher.id,
            week_start_date=week_start,
            week_end_date=date(2026, 10, 25),
            data_origin="TEST",
        )
        db.add(week)
        db.commit()

        yield {
            "db": db,
            "teacher": teacher,
            "recipients": [recipient for recipient, _ in recipients],
            "extra_teachers": extra_teachers,
            "week": week,
            "division": division,
            "week_start": week_start,
        }
    finally:
        db.rollback()

        # Delete only notifications and planning records belonging to this fixture.
        if teacher is not None:
            db.query(PlanningNotification).filter(
                PlanningNotification.para_teacher_id == teacher.id
            ).delete(synchronize_session=False)

            if week is not None:
                db.query(SessionPlanItem).filter(
                    SessionPlanItem.session_plan_week_id == week.id
                ).delete(synchronize_session=False)
                db.query(SessionPlanWeek).filter(
                    SessionPlanWeek.id == week.id
                ).delete(synchronize_session=False)

            db.query(UserAssignment).filter(
                UserAssignment.user_id == teacher.id
            ).delete(synchronize_session=False)
            db.query(UserRole).filter(
                UserRole.user_id == teacher.id
            ).delete(synchronize_session=False)

        for extra_teacher in extra_teachers:
            db.query(PlanningNotification).filter(
                PlanningNotification.para_teacher_id == extra_teacher.id
            ).delete(synchronize_session=False)
            db.query(SessionPlanWeek).filter(
                SessionPlanWeek.para_teacher_id == extra_teacher.id
            ).delete(synchronize_session=False)
            db.query(UserAssignment).filter(
                UserAssignment.user_id == extra_teacher.id
            ).delete(synchronize_session=False)
            db.query(UserRole).filter(
                UserRole.user_id == extra_teacher.id
            ).delete(synchronize_session=False)
            db.query(User).filter(
                User.id == extra_teacher.id
            ).delete(synchronize_session=False)

        recipient_ids = [recipient.id for recipient, _ in recipients]
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
            db.query(User).filter(User.id == teacher.id).delete(
                synchronize_session=False
            )

        if division is not None:
            db.query(ClassDivision).filter(
                ClassDivision.id == division.id
            ).delete(synchronize_session=False)

        if school is not None:
            db.query(School).filter(School.id == school.id).delete(
                synchronize_session=False
            )

        db.commit()
        db.close()


def _add_planned_items(db, fixture, count):
    week = fixture["week"]
    division = fixture["division"]

    existing = (
        db.query(SessionPlanItem)
        .filter(SessionPlanItem.session_plan_week_id == week.id)
        .all()
    )
    for item in existing:
        db.delete(item)
    db.flush()

    for sequence in range(1, count + 1):
        db.add(
            SessionPlanItem(
                session_plan_week_id=week.id,
                class_division_id=division.id,
                planned_date=date(2026, 10, 19 + (sequence - 1) % 7),
                sequence_no=sequence,
                data_origin="TEST",
            )
        )
    db.flush()


def _add_holiday(db, planned_date, *, year_active=True, holiday_active=True):
    suffix = uuid4().hex[:10]
    year = AcademicYear(
        name=f"PN-YEAR-{suffix}",
        start_date=date(2026, 1, 1),
        end_date=date(2027, 12, 31),
        is_active=year_active,
        data_origin="TEST",
    )
    db.add(year)
    db.flush()

    holiday = AcademicHoliday(
        academic_year_id=year.id,
        holiday_date=planned_date,
        name=f"Planning Test Holiday {suffix}",
        type="PUBLIC",
        is_active=holiday_active,
        data_origin="TEST",
    )
    db.add(holiday)
    db.flush()
    return year, holiday


def test_weekly_shortfall_notifies_management_and_coordinator(
    planning_notification_fixture,
):
    fixture = planning_notification_fixture
    db = fixture["db"]
    service = PlanningNotificationService()
    _add_planned_items(db, fixture, 5)

    service.generate_weekly_noncompliance(
        db,
        week_start_date=fixture["week_start"],
    )
    db.flush()

    fixture_notifications = db.query(PlanningNotification).filter(
        PlanningNotification.para_teacher_id == fixture["teacher"].id,
        PlanningNotification.week_start_date == fixture["week_start"],
        PlanningNotification.notification_type == service.WEEKLY_NONCOMPLIANCE,
    ).all()

    expected_recipient_ids = {
        recipient.id for recipient in fixture["recipients"]
    }

    assert expected_recipient_ids.issubset({
        notification.recipient_id for notification in fixture_notifications
    })
    assert all(
        not notification.is_read
        for notification in fixture_notifications
        if notification.recipient_id in expected_recipient_ids
    )
    assert len(fixture_notifications) >= len(expected_recipient_ids)



def test_weekly_shortfall_rerun_does_not_duplicate_notifications(
    planning_notification_fixture,
):
    fixture = planning_notification_fixture
    db = fixture["db"]
    service = PlanningNotificationService()
    _add_planned_items(db, fixture, 4)

    service.generate_weekly_noncompliance(
        db,
        week_start_date=fixture["week_start"],
    )
    db.flush()

    first_ids = {
        notification.id
        for notification in db.query(PlanningNotification).filter(
            PlanningNotification.para_teacher_id == fixture["teacher"].id,
            PlanningNotification.week_start_date == fixture["week_start"],
        )
    }

    service.generate_weekly_noncompliance(
        db,
        week_start_date=fixture["week_start"],
    )
    db.flush()

    current = db.query(PlanningNotification).filter(
        PlanningNotification.para_teacher_id == fixture["teacher"].id,
        PlanningNotification.week_start_date == fixture["week_start"],
    ).all()

    assert len(current) == len(first_ids)
    assert {notification.id for notification in current} == first_ids


def test_compliance_restores_then_reactivates_existing_notifications(
    planning_notification_fixture,
):
    fixture = planning_notification_fixture
    db = fixture["db"]
    service = PlanningNotificationService()
    _add_planned_items(db, fixture, 5)

    service.generate_weekly_noncompliance(
        db,
        week_start_date=fixture["week_start"],
    )
    db.flush()

    before = {
        notification.recipient_id: notification.id
        for notification in db.query(PlanningNotification).filter(
            PlanningNotification.para_teacher_id == fixture["teacher"].id,
            PlanningNotification.week_start_date == fixture["week_start"],
        )
    }
    assert {
        recipient.id for recipient in fixture["recipients"]
    }.issubset(before)

    _add_planned_items(
        db,
        fixture,
        AcademicCalendarService.MINIMUM_WEEKLY_SESSIONS,
    )
    service.generate_weekly_noncompliance(
        db,
        week_start_date=fixture["week_start"],
    )
    db.flush()

    resolved = db.query(PlanningNotification).filter(
        PlanningNotification.para_teacher_id == fixture["teacher"].id,
        PlanningNotification.week_start_date == fixture["week_start"],
    ).all()
    assert len(resolved) == len(before)
    assert all(notification.is_read for notification in resolved)
    assert {notification.recipient_id: notification.id for notification in resolved} == before

    _add_planned_items(db, fixture, 3)
    service.generate_weekly_noncompliance(
        db,
        week_start_date=fixture["week_start"],
    )
    db.flush()

    reactivated = db.query(PlanningNotification).filter(
        PlanningNotification.para_teacher_id == fixture["teacher"].id,
        PlanningNotification.week_start_date == fixture["week_start"],
    ).all()
    assert len(reactivated) == len(before)
    assert all(notification.is_read is False for notification in reactivated)
    assert {notification.recipient_id: notification.id for notification in reactivated} == before


def test_weekly_generator_requires_monday(planning_notification_fixture):
    fixture = planning_notification_fixture

    with pytest.raises(ValueError, match="must be a Monday"):
        PlanningNotificationService().generate_weekly_noncompliance(
            fixture["db"],
            week_start_date=date(2026, 10, 20),
        )


def test_former_management_recipient_notification_is_marked_read(
    planning_notification_fixture,
):
    fixture = planning_notification_fixture
    db = fixture["db"]
    service = PlanningNotificationService()
    _add_planned_items(db, fixture, 5)

    service.generate_weekly_noncompliance(
        db,
        week_start_date=fixture["week_start"],
    )
    db.flush()

    former_recipient = fixture["recipients"][0]
    notification = (
        db.query(PlanningNotification)
        .filter(
            PlanningNotification.recipient_id == former_recipient.id,
            PlanningNotification.para_teacher_id == fixture["teacher"].id,
            PlanningNotification.week_start_date == fixture["week_start"],
            PlanningNotification.notification_type
            == service.WEEKLY_NONCOMPLIANCE,
        )
        .one()
    )
    assert notification.is_read is False

    db.query(UserRole).filter(
        UserRole.user_id == former_recipient.id
    ).update(
        {UserRole.is_active: False},
        synchronize_session=False,
    )
    db.flush()

    service.generate_weekly_noncompliance(
        db,
        week_start_date=fixture["week_start"],
    )
    db.flush()
    db.refresh(notification)

    assert notification.is_read is True

    # The still-active management recipient continues to receive the alert.
    current_recipient = fixture["recipients"][1]
    current_notification = (
        db.query(PlanningNotification)
        .filter(
            PlanningNotification.recipient_id == current_recipient.id,
            PlanningNotification.para_teacher_id == fixture["teacher"].id,
            PlanningNotification.week_start_date == fixture["week_start"],
            PlanningNotification.notification_type
            == service.WEEKLY_NONCOMPLIANCE,
        )
        .one()
    )
    assert current_notification.is_read is False


def test_no_management_recipients_creates_no_new_notifications(
    planning_notification_fixture,
):
    fixture = planning_notification_fixture
    db = fixture["db"]
    service = PlanningNotificationService()
    _add_planned_items(db, fixture, 2)

    for recipient in fixture["recipients"]:
        db.query(UserRole).filter(
            UserRole.user_id == recipient.id
        ).update(
            {UserRole.is_active: False},
            synchronize_session=False,
        )
    db.flush()

    notifications = service.generate_weekly_noncompliance(
        db,
        week_start_date=fixture["week_start"],
    )

    fixture_recipient_ids = {
        recipient.id for recipient in fixture["recipients"]
    }
    assert not any(
        notification.recipient_id in fixture_recipient_ids
        for notification in notifications
    )
    assert db.query(PlanningNotification).filter(
        PlanningNotification.para_teacher_id == fixture["teacher"].id,
        PlanningNotification.week_start_date == fixture["week_start"],
        PlanningNotification.recipient_id.in_(fixture_recipient_ids),
    ).count() == 0


def test_weekly_notifications_resolve_when_no_teachers_remain_eligible(
    planning_notification_fixture,
):
    fixture = planning_notification_fixture
    db = fixture["db"]
    service = PlanningNotificationService()
    _add_planned_items(db, fixture, 3)

    service.generate_weekly_noncompliance(
        db,
        week_start_date=fixture["week_start"],
    )
    db.flush()

    notifications = db.query(PlanningNotification).filter(
        PlanningNotification.para_teacher_id == fixture["teacher"].id,
        PlanningNotification.week_start_date == fixture["week_start"],
        PlanningNotification.notification_type == service.WEEKLY_NONCOMPLIANCE,
    ).all()
    assert len(notifications) >= len(fixture["recipients"])
    assert all(not notification.is_read for notification in notifications)

    db.query(User).filter(
        User.id == fixture["teacher"].id
    ).update(
        {User.status: "INACTIVE"},
        synchronize_session=False,
    )
    db.flush()

    resolved = service.generate_weekly_noncompliance(
        db,
        week_start_date=fixture["week_start"],
    )
    db.flush()

    resolved_ids = {notification.id for notification in resolved}
    assert {notification.id for notification in notifications}.issubset(
        resolved_ids
    )
    assert all(notification.is_read for notification in notifications)


def test_weekly_reconciliation_returns_unique_notification_ids(
    planning_notification_fixture,
):
    fixture = planning_notification_fixture
    db = fixture["db"]
    service = PlanningNotificationService()
    _add_planned_items(db, fixture, 3)

    service.generate_weekly_noncompliance(
        db,
        week_start_date=fixture["week_start"],
    )
    db.flush()

    # Make the teacher ineligible so existing alerts are reconciled.
    db.query(User).filter(
        User.id == fixture["teacher"].id
    ).update(
        {User.status: "INACTIVE"},
        synchronize_session=False,
    )
    db.flush()

    notifications = service.generate_weekly_noncompliance(
        db,
        week_start_date=fixture["week_start"],
    )

    notification_ids = [
        notification.id for notification in notifications
    ]
    assert len(notification_ids) == len(set(notification_ids))


def test_weekly_notifications_resolve_for_ineligible_teacher_while_others_remain(
    planning_notification_fixture,
):
    fixture = planning_notification_fixture
    db = fixture["db"]
    service = PlanningNotificationService()
    _add_planned_items(db, fixture, 3)

    service.generate_weekly_noncompliance(
        db,
        week_start_date=fixture["week_start"],
    )
    db.flush()

    former_teacher_notifications = db.query(PlanningNotification).filter(
        PlanningNotification.para_teacher_id == fixture["teacher"].id,
        PlanningNotification.week_start_date == fixture["week_start"],
        PlanningNotification.notification_type == service.WEEKLY_NONCOMPLIANCE,
    ).all()
    assert len(former_teacher_notifications) >= len(fixture["recipients"])
    assert all(
        not notification.is_read for notification in former_teacher_notifications
    )

    suffix = uuid4().hex[:10]
    other_teacher = User(
        user_code=f"PN-T2-{suffix}",
        full_name="Second Planning Test Teacher",
        email=f"pn-teacher2-{suffix}@example.com",
        password_hash="test-only-not-a-real-password",
        status="ACTIVE",
        data_origin="TEST",
    )
    db.add(other_teacher)
    db.flush()
    fixture["extra_teachers"].append(other_teacher)

    teacher_role = db.query(Role).filter(Role.code == "PARA_TEACHER").one()
    db.add(
        UserRole(
            user_id=other_teacher.id,
            role_id=teacher_role.id,
            is_active=True,
        )
    )
    db.add(
        UserAssignment(
            user_id=other_teacher.id,
            scope_type="SCHOOL",
            school_id=fixture["division"].school_id,
            start_date=date(2026, 1, 1),
            is_active=True,
        )
    )
    db.add(
        SessionPlanWeek(
            para_teacher_id=other_teacher.id,
            week_start_date=fixture["week_start"],
            week_end_date=date(2026, 10, 25),
            data_origin="TEST",
        )
    )
    db.flush()

    db.query(UserAssignment).filter(
        UserAssignment.user_id == fixture["teacher"].id
    ).update(
        {UserAssignment.is_active: False},
        synchronize_session=False,
    )
    db.flush()

    service.generate_weekly_noncompliance(
        db,
        week_start_date=fixture["week_start"],
    )
    db.flush()

    assert all(
        notification.is_read for notification in former_teacher_notifications
    )

    other_teacher_notifications = db.query(PlanningNotification).filter(
        PlanningNotification.para_teacher_id == other_teacher.id,
        PlanningNotification.week_start_date == fixture["week_start"],
        PlanningNotification.notification_type == service.WEEKLY_NONCOMPLIANCE,
    ).all()
    assert len(other_teacher_notifications) >= len(fixture["recipients"])
    assert all(not notification.is_read for notification in other_teacher_notifications)


def test_overdue_item_notifies_only_owning_para_teacher(
    planning_notification_fixture,
):
    fixture = planning_notification_fixture
    db = fixture["db"]
    service = PlanningNotificationService()
    _add_planned_items(db, fixture, 1)

    item = (
        db.query(SessionPlanItem)
        .filter(SessionPlanItem.session_plan_week_id == fixture["week"].id)
        .one()
    )

    notification = service.generate_reschedule_required(
        db,
        session_plan_item_id=item.id,
        current_date=date(2026, 10, 27),
    )
    db.flush()

    assert notification is not None
    assert notification.notification_type == service.RESCHEDULE_REQUIRED
    assert notification.recipient_id == fixture["teacher"].id
    assert notification.para_teacher_id == fixture["teacher"].id
    assert notification.session_plan_item_id == item.id
    assert notification.week_start_date is None

    assert db.query(PlanningNotification).filter(
        PlanningNotification.session_plan_item_id == item.id,
        PlanningNotification.notification_type == service.RESCHEDULE_REQUIRED,
    ).count() == 1


def test_overdue_item_rerun_reuses_existing_notification(
    planning_notification_fixture,
):
    fixture = planning_notification_fixture
    db = fixture["db"]
    service = PlanningNotificationService()
    _add_planned_items(db, fixture, 1)

    item = (
        db.query(SessionPlanItem)
        .filter(SessionPlanItem.session_plan_week_id == fixture["week"].id)
        .one()
    )

    first = service.generate_reschedule_required(
        db,
        session_plan_item_id=item.id,
        current_date=date(2026, 10, 27),
    )
    second = service.generate_reschedule_required(
        db,
        session_plan_item_id=item.id,
        current_date=date(2026, 10, 28),
    )
    db.flush()

    assert first is not None
    assert second is not None
    assert first.id == second.id
    assert db.query(PlanningNotification).filter(
        PlanningNotification.session_plan_item_id == item.id,
        PlanningNotification.notification_type == service.RESCHEDULE_REQUIRED,
    ).count() == 1


def test_completed_session_resolves_existing_reschedule_notification(
    planning_notification_fixture,
):
    fixture = planning_notification_fixture
    db = fixture["db"]
    service = PlanningNotificationService()
    _add_planned_items(db, fixture, 1)

    item = (
        db.query(SessionPlanItem)
        .filter(SessionPlanItem.session_plan_week_id == fixture["week"].id)
        .one()
    )

    notification = service.generate_reschedule_required(
        db,
        session_plan_item_id=item.id,
        current_date=date(2026, 10, 27),
    )
    db.flush()

    assert notification is not None
    assert notification.is_read is False

    teaching_session = TeachingSession(
        session_plan_item_id=item.id,
        class_division_id=fixture["division"].id,
        para_teacher_id=fixture["teacher"].id,
        session_date=item.planned_date,
        status="COMPLETED",
        data_origin="TEST",
    )
    db.add(teaching_session)
    db.flush()

    result = service.generate_reschedule_required(
        db,
        session_plan_item_id=item.id,
        current_date=date(2026, 10, 27),
    )
    db.flush()
    db.refresh(notification)

    assert result is None
    assert notification.is_read is True
    assert (
        db.query(PlanningNotification)
        .filter(
            PlanningNotification.session_plan_item_id == item.id,
            PlanningNotification.notification_type
            == service.RESCHEDULE_REQUIRED,
        )
        .count()
        == 1
    )


def test_completed_teaching_session_does_not_trigger_reschedule(
    planning_notification_fixture,
):
    fixture = planning_notification_fixture
    db = fixture["db"]
    service = PlanningNotificationService()
    _add_planned_items(db, fixture, 1)

    item = (
        db.query(SessionPlanItem)
        .filter(SessionPlanItem.session_plan_week_id == fixture["week"].id)
        .one()
    )
    teaching_session = TeachingSession(
        session_plan_item_id=item.id,
        class_division_id=fixture["division"].id,
        para_teacher_id=fixture["teacher"].id,
        session_date=item.planned_date,
        status="COMPLETED",
        data_origin="TEST",
    )
    db.add(teaching_session)
    db.flush()

    notification = service.generate_reschedule_required(
        db,
        session_plan_item_id=item.id,
        current_date=date(2026, 10, 27),
    )

    assert notification is None
    assert db.query(PlanningNotification).filter(
        PlanningNotification.session_plan_item_id == item.id,
        PlanningNotification.notification_type == service.RESCHEDULE_REQUIRED,
    ).count() == 0


def test_item_with_no_reschedule_condition_creates_no_notification(
    planning_notification_fixture,
):
    fixture = planning_notification_fixture
    db = fixture["db"]
    service = PlanningNotificationService()
    _add_planned_items(db, fixture, 1)

    item = (
        db.query(SessionPlanItem)
        .filter(SessionPlanItem.session_plan_week_id == fixture["week"].id)
        .one()
    )

    notification = service.generate_reschedule_required(
        db,
        session_plan_item_id=item.id,
        current_date=item.planned_date,
        current_datetime=None,
    )

    assert notification is None
    assert db.query(PlanningNotification).filter(
        PlanningNotification.session_plan_item_id == item.id,
        PlanningNotification.notification_type == service.RESCHEDULE_REQUIRED,
    ).count() == 0


def test_active_holiday_triggers_reschedule_notification(
    planning_notification_fixture,
):
    fixture = planning_notification_fixture
    db = fixture["db"]
    _add_planned_items(db, fixture, 1)

    item = (
        db.query(SessionPlanItem)
        .filter(SessionPlanItem.session_plan_week_id == fixture["week"].id)
        .one()
    )
    year, holiday = _add_holiday(db, item.planned_date)

    notification = PlanningNotificationService().generate_reschedule_required(
        db,
        session_plan_item_id=item.id,
        current_date=item.planned_date,
    )

    assert notification is not None
    assert notification.notification_type == "SESSION_RESCHEDULE_REQUIRED"
    assert notification.recipient_id == fixture["teacher"].id
    assert notification.session_plan_item_id == item.id

    db.delete(holiday)
    db.delete(year)
    db.flush()


@pytest.mark.parametrize(
    ("year_active", "holiday_active"),
    [
        (False, True),
        (True, False),
    ],
)
def test_inactive_holiday_or_academic_year_does_not_trigger_reschedule(
    planning_notification_fixture,
    year_active,
    holiday_active,
):
    fixture = planning_notification_fixture
    db = fixture["db"]
    _add_planned_items(db, fixture, 1)

    item = (
        db.query(SessionPlanItem)
        .filter(SessionPlanItem.session_plan_week_id == fixture["week"].id)
        .one()
    )
    year, holiday = _add_holiday(
        db,
        item.planned_date,
        year_active=year_active,
        holiday_active=holiday_active,
    )

    notification = PlanningNotificationService().generate_reschedule_required(
        db,
        session_plan_item_id=item.id,
        current_date=item.planned_date,
    )

    assert notification is None
    assert db.query(PlanningNotification).filter(
        PlanningNotification.session_plan_item_id == item.id,
        PlanningNotification.notification_type
        == "SESSION_RESCHEDULE_REQUIRED",
    ).count() == 0

    db.delete(holiday)
    db.delete(year)
    db.flush()