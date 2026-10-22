from __future__ import annotations

import os
from datetime import date, time, timedelta
from uuid import UUID, uuid4
from unittest.mock import patch

import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models import (
    AcademicHoliday,
    AcademicYear,
    ClassDivision,
    Role,
    SessionPlanItem,
    SessionPlanWeek,
    User,
    UserAssignment,
    UserRole,
    PlanningNotification,
    Permission,
    RolePermission,
)
from app.services.academic_calendar.service import AcademicCalendarService
from app.services.session_plan.service import SessionPlanService


load_dotenv()

DEMO_PASSWORD = os.getenv("DEMO_USER_PASSWORD")
if not DEMO_PASSWORD:
    raise RuntimeError(
        "DEMO_USER_PASSWORD must be configured in .env "
        "before running academic-calendar API tests."
    )

client = TestClient(app)
PARA_TEACHER_EMAIL = "pt001@demo.vigyan.com"
SECOND_TEACHER_EMAIL = "pt002@demo.vigyan.com"


def login(email: str) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": DEMO_PASSWORD},
    )
    assert response.status_code == 200, response.text
    return response.json()["session_token"]


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def user_id(email: str) -> UUID:
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).one()
        return user.id
    finally:
        db.close()


@pytest.fixture
def calendar_setup():
    db = SessionLocal()
    year = AcademicYear(
        name=f"API-{uuid4()}",
        start_date=date(2026, 10, 1),
        end_date=date(2027, 9, 30),
        is_active=True,
        data_origin="TEST",
    )
    db.add(year)
    db.flush()

    teacher_id = user_id(PARA_TEACHER_EMAIL)
    teacher = db.query(User).filter(User.id == teacher_id).one()

    assignment = (
        db.query(UserAssignment)
        .filter(
            UserAssignment.user_id == teacher_id,
            UserAssignment.is_active.is_(True),
            UserAssignment.school_id.is_not(None),
        )
        .order_by(UserAssignment.start_date.desc())
        .first()
    )
    if assignment is None:
        db.rollback()
        db.close()
        pytest.skip("Demo para-teacher school assignment is required.")

    # Dedicated test teacher prevents dependence on populated demo planning weeks.
    test_teacher_email = f"calendar-pt-{uuid4()}@example.com"
    test_teacher = User(
        user_code=f"CAL-PT-{uuid4().hex[:8]}",
        full_name="Academic Calendar API Test Para Teacher",
        email=test_teacher_email,
        password_hash=teacher.password_hash,
        status="ACTIVE",
        data_origin="TEST",
    )
    db.add(test_teacher)
    db.flush()

    para_teacher_role = db.query(Role).filter(Role.code == "PARA_TEACHER").one()
    db.add(
        UserRole(
            user_id=test_teacher.id,
            role_id=para_teacher_role.id,
            is_active=True,
        )
    )
    db.add(
        UserAssignment(
            user_id=test_teacher.id,
            scope_type="SCHOOL",
            school_id=assignment.school_id,
            start_date=date(2020, 1, 1),
            end_date=None,
            is_active=True,
        )
    )
    db.flush()

    admin_email = f"calendar-admin-{uuid4()}@example.com"
    admin = User(
        user_code=f"CAL-ADMIN-{uuid4().hex[:8]}",
        full_name="Calendar API Test Administrator",
        email=admin_email,
        password_hash=teacher.password_hash,
        status="ACTIVE",
        data_origin="TEST",
    )
    db.add(admin)
    db.flush()

    data_manager_email = f"calendar-dm-{uuid4()}@example.com"
    data_manager = User(
        user_code=f"CAL-DM-{uuid4().hex[:8]}",
        full_name="Calendar API Test Data Manager",
        email=data_manager_email,
        password_hash=teacher.password_hash,
        status="ACTIVE",
        data_origin="TEST",
    )
    db.add(data_manager)
    db.flush()

    db.add_all(
        [
            UserRole(
                user_id=admin.id,
                role_id=db.query(Role).filter(Role.code == "PLATFORM_OWNER").one().id,
                is_active=True,
            ),
            UserRole(
                user_id=data_manager.id,
                role_id=db.query(Role).filter(Role.code == "DATA_MANAGER").one().id,
                is_active=True,
            ),
        ]
    )

    cross_teacher_role_emails = {}
    for role_code in ("STEM_COORDINATOR", "MANAGEMENT", "SYSTEM_ADMIN"):
        email = f"calendar-{role_code.lower()}-{uuid4()}@example.com"
        role_user = User(
            user_code=f"CAL-{role_code[:4]}-{uuid4().hex[:8]}",
            full_name=f"Calendar API Test {role_code}",
            email=email,
            password_hash=teacher.password_hash,
            status="ACTIVE",
            data_origin="TEST",
        )
        db.add(role_user)
        db.flush()
        role = db.query(Role).filter(Role.code == role_code).one()
        db.add(UserRole(user_id=role_user.id, role_id=role.id, is_active=True))
        cross_teacher_role_emails[role_code] = email

    db.flush()

    class_division = (
        db.query(ClassDivision)
        .filter(
            ClassDivision.school_id == assignment.school_id,
            ClassDivision.data_origin == "DEMO",
        )
        .order_by(ClassDivision.id)
        .first()
    )
    if class_division is None:
        db.rollback()
        db.close()
        pytest.skip("Demo class division is required.")

    week_start = date(2027, 1, 4)
    latest_week_start = date(2027, 9, 20)
    while week_start <= latest_week_start:
        existing_week = (
            db.query(SessionPlanWeek)
            .filter(
                SessionPlanWeek.para_teacher_id == test_teacher.id,
                SessionPlanWeek.week_start_date == week_start,
            )
            .first()
        )
        if existing_week is None:
            break
        week_start += timedelta(days=7)

    if week_start > latest_week_start:
        db.rollback()
        db.close()
        pytest.skip("No free planning week within the fixture academic year.")

    assert date(2026, 10, 1) <= week_start
    assert week_start + timedelta(days=6) <= date(2027, 9, 30)

    service = SessionPlanService()
    week = service.get_or_create_week(
        db,
        para_teacher_id=test_teacher.id,
        week_start_date=week_start,
        data_origin="TEST",
    )
    item = service.create_item(
        db,
        para_teacher_id=test_teacher.id,
        session_plan_week_id=week.id,
        class_division_id=class_division.id,
        planned_date=week_start,
        sequence_no=1,
        planned_start_time=time(9, 0),
        planned_end_time=time(9, 45),
        data_origin="TEST",
    )
    db.commit()

    result = {
        "year_id": year.id,
        "teacher_id": teacher_id,
        "test_teacher_id": test_teacher.id,
        "test_teacher_email": test_teacher_email,
        "admin_email": admin_email,
        "data_manager_email": data_manager_email,
        "cross_teacher_role_emails": cross_teacher_role_emails,
        "item_id": item.id,
        "week_id": week.id,
        "week_start": week_start,
        "holiday_ids": [],
    }
    db.close()
    yield result

    cleanup = SessionLocal()
    try:
        test_emails = [
            result["test_teacher_email"],
            result["admin_email"],
            result["data_manager_email"],
            *result["cross_teacher_role_emails"].values(),
        ]
        rows = cleanup.query(User.id).filter(User.email.in_(test_emails)).all()
        test_user_ids = [row[0] for row in rows]

        cleanup.query(SessionPlanItem).filter(
            SessionPlanItem.id == result["item_id"]
        ).delete(synchronize_session=False)
        cleanup.query(SessionPlanWeek).filter(
            SessionPlanWeek.id == result["week_id"]
        ).delete(synchronize_session=False)
        cleanup.query(AcademicHoliday).filter(
            AcademicHoliday.academic_year_id == result["year_id"]
        ).delete(synchronize_session=False)
        cleanup.query(AcademicYear).filter(
            AcademicYear.id == result["year_id"]
        ).delete(synchronize_session=False)

        if test_user_ids:
            cleanup.query(UserRole).filter(
                UserRole.user_id.in_(test_user_ids)
            ).delete(synchronize_session=False)
            cleanup.query(UserAssignment).filter(
                UserAssignment.user_id.in_(test_user_ids)
            ).delete(synchronize_session=False)
            cleanup.query(User).filter(User.id.in_(test_user_ids)).delete(
                synchronize_session=False
            )
        cleanup.commit()
    finally:
        cleanup.close()


def test_calendar_requires_authentication(calendar_setup):
    response = client.get(
        "/api/v1/academic-calendar",
        params={"start_date": "2027-01-01", "end_date": "2027-01-03"},
    )
    assert response.status_code == 401


def test_para_teacher_can_view_own_calendar(calendar_setup):
    token = login(calendar_setup["test_teacher_email"])
    db = SessionLocal()
    try:
        fixture_year = (
            db.query(AcademicYear)
            .filter(AcademicYear.id == calendar_setup["year_id"])
            .one()
        )
    finally:
        db.close()

    with patch.object(
        AcademicCalendarService,
        "get_active_academic_year",
        return_value=fixture_year,
    ):
        response = client.get(
            "/api/v1/academic-calendar",
            headers=auth_headers(token),
            params={
                "start_date": calendar_setup["week_start"].isoformat(),
                "end_date": (
                    calendar_setup["week_start"] + timedelta(days=6)
                ).isoformat(),
            },
        )

    assert response.status_code == 200, response.text
    days = response.json()
    assert len(days) == 7
    assert days[5]["is_working_day"] is False
    assert days[6]["is_working_day"] is False
    assert any(
        session["session_plan_item_id"] == str(calendar_setup["item_id"])
        for day in days
        for session in day["sessions"]
    )


def test_para_teacher_cannot_view_another_teacher_calendar(calendar_setup):
    token = login(PARA_TEACHER_EMAIL)
    response = client.get(
        "/api/v1/academic-calendar",
        headers=auth_headers(token),
        params={
            "para_teacher_id": str(user_id(SECOND_TEACHER_EMAIL)),
            "start_date": "2026-10-01",
            "end_date": "2026-10-03",
        },
    )
    assert response.status_code == 403


@pytest.mark.parametrize(
    "role_code",
    ["DATA_MANAGER", "STEM_COORDINATOR", "MANAGEMENT", "SYSTEM_ADMIN"],
)
def test_project_wide_roles_can_view_another_teacher_calendar(calendar_setup, role_code):
    email = (
        calendar_setup["data_manager_email"]
        if role_code == "DATA_MANAGER"
        else calendar_setup["cross_teacher_role_emails"][role_code]
    )
    token = login(email)
    response = client.get(
        "/api/v1/academic-calendar",
        headers=auth_headers(token),
        params={
            "para_teacher_id": str(user_id(SECOND_TEACHER_EMAIL)),
            "start_date": "2026-10-01",
            "end_date": "2026-10-03",
        },
    )
    assert response.status_code == 200, response.text


def test_data_manager_can_manage_holidays_and_list_them(calendar_setup):
    token = login(calendar_setup["data_manager_email"])
    db = SessionLocal()
    try:
        fixture_year = (
            db.query(AcademicYear)
            .filter(AcademicYear.id == calendar_setup["year_id"])
            .one()
        )
        occupied_dates = {
            row[0]
            for row in db.query(AcademicHoliday.holiday_date)
            .filter(
                AcademicHoliday.academic_year_id == calendar_setup["year_id"],
                AcademicHoliday.is_active.is_(True),
            )
            .all()
        }
    finally:
        db.close()

    holiday_day = date(2027, 1, 5)
    while holiday_day <= date(2027, 9, 30) and holiday_day in occupied_dates:
        holiday_day += timedelta(days=1)
    assert holiday_day <= date(2027, 9, 30), "Fixture year has no free holiday date."

    with patch.object(
        AcademicCalendarService,
        "get_active_academic_year",
        return_value=fixture_year,
    ):
        created = client.post(
            "/api/v1/academic-calendar/holidays",
            headers=auth_headers(token),
            json={
                "holiday_date": holiday_day.isoformat(),
                "name": "API Test Holiday",
                "type": "TEST",
            },
        )
        assert created.status_code == 201, created.text
        holiday_id = created.json()["id"]

        listed = client.get(
            "/api/v1/academic-calendar/holidays",
            headers=auth_headers(token),
        )
        assert listed.status_code == 200
        assert any(row["id"] == holiday_id for row in listed.json())

        updated = client.patch(
            f"/api/v1/academic-calendar/holidays/{holiday_id}",
            headers=auth_headers(token),
            json={"name": "Updated API Test Holiday"},
        )
        assert updated.status_code == 200
        assert updated.json()["name"] == "Updated API Test Holiday"

        deactivated = client.delete(
            f"/api/v1/academic-calendar/holidays/{holiday_id}",
            headers=auth_headers(token),
        )
        assert deactivated.status_code == 200
        assert deactivated.json()["is_active"] is False


def test_para_teacher_cannot_manage_holidays(calendar_setup):
    token = login(PARA_TEACHER_EMAIL)
    response = client.post(
        "/api/v1/academic-calendar/holidays",
        headers=auth_headers(token),
        json={
            "holiday_date": "2026-10-03",
            "name": "Unauthorized",
            "type": "TEST",
        },
    )
    assert response.status_code == 403


def test_calendar_reschedule_updates_existing_plan_item(calendar_setup):
    token = login(calendar_setup["test_teacher_email"])
    response = client.patch(
        f"/api/v1/academic-calendar/sessions/{calendar_setup['item_id']}/reschedule",
        headers=auth_headers(token),
        json={
            "planned_date": (
                calendar_setup["week_start"] + timedelta(days=1)
            ).isoformat(),
            "planned_start_time": "10:00:00",
            "planned_end_time": "10:45:00",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["id"] == str(calendar_setup["item_id"])
    assert response.json()["planned_date"] == (
        calendar_setup["week_start"] + timedelta(days=1)
    ).isoformat()
    assert response.json()["planned_start_time"] == "10:00:00"


def test_calendar_reschedule_rejects_invalid_time_pair(calendar_setup):
    token = login(calendar_setup["test_teacher_email"])
    response = client.patch(
        f"/api/v1/academic-calendar/sessions/{calendar_setup['item_id']}/reschedule",
        headers=auth_headers(token),
        json={
            "planned_date": (
                calendar_setup["week_start"] + timedelta(days=1)
            ).isoformat(),
            "planned_start_time": "10:00:00",
        },
    )
    assert response.status_code == 422


def test_project_wide_user_can_view_planning_compliance(calendar_setup):
    token = login(calendar_setup["admin_email"])
    response = client.get(
        f"/api/v1/academic-calendar/compliance/{calendar_setup['week_start'].isoformat()}",
        headers=auth_headers(token),
    )
    assert response.status_code == 200, response.text
    matching = [
        row
        for row in response.json()
        if row["para_teacher_id"] == str(calendar_setup["test_teacher_id"])
    ]
    assert matching
    assert matching[0]["planned_session_count"] == 1
    assert matching[0]["minimum_met"] is False


def test_planning_notifications_requires_authentication():
    response = client.get("/api/v1/notifications/planning")
    assert response.status_code == 401


def test_para_teacher_can_view_own_planning_notifications(calendar_setup):
    token = login(calendar_setup["test_teacher_email"])

    response = client.get(
        "/api/v1/notifications/planning",
        headers=auth_headers(token),
    )

    assert response.status_code == 200, response.text
    assert isinstance(response.json(), list)


def test_planning_notifications_requires_permission(calendar_setup):

    db = SessionLocal()
    removed_link = None

    try:
        role = db.query(Role).filter(Role.code == "DATA_MANAGER").one()
        permission = (
            db.query(Permission)
            .filter(Permission.code == "planning_notification.view")
            .one()
        )
        removed_link = (
            db.query(RolePermission)
            .filter(
                RolePermission.role_id == role.id,
                RolePermission.permission_id == permission.id,
            )
            .one_or_none()
        )

        assert removed_link is not None, (
            "Expected the seeded Data Manager permission link to exist."
        )

        db.delete(removed_link)
        db.commit()
    finally:
        db.close()

    try:
        token = login(calendar_setup["data_manager_email"])
        response = client.get(
            "/api/v1/notifications/planning",
            headers=auth_headers(token),
        )
        assert response.status_code == 403, response.text
    finally:
        restore_db = SessionLocal()
        try:
            role = (
                restore_db.query(Role)
                .filter(Role.code == "DATA_MANAGER")
                .one()
            )
            permission = (
                restore_db.query(Permission)
                .filter(Permission.code == "planning_notification.view")
                .one()
            )
            link_exists = (
                restore_db.query(RolePermission)
                .filter(
                    RolePermission.role_id == role.id,
                    RolePermission.permission_id == permission.id,
                )
                .first()
            )
            if link_exists is None:
                restore_db.add(
                    RolePermission(
                        role_id=role.id,
                        permission_id=permission.id,
                    )
                )
                restore_db.commit()
        finally:
            restore_db.close()


def test_planning_notifications_only_returns_current_users_records(
    calendar_setup,
):
    from datetime import date

    recipient_id = calendar_setup["test_teacher_id"]
    other_recipient_id = calendar_setup["teacher_id"]
    para_teacher_id = calendar_setup["test_teacher_id"]

    db = SessionLocal()
    notification_ids = []
    try:
        notifications = [
            PlanningNotification(
                recipient_id=recipient_id,
                notification_type="WEEKLY_PLANNING_NONCOMPLIANCE",
                para_teacher_id=para_teacher_id,
                week_start_date=date(2026, 10, 19),
                message="Test notification for current recipient",
            ),
            PlanningNotification(
                recipient_id=other_recipient_id,
                notification_type="WEEKLY_PLANNING_NONCOMPLIANCE",
                para_teacher_id=para_teacher_id,
                week_start_date=date(2026, 10, 19),
                message="Test notification for another recipient",
            ),
        ]
        db.add_all(notifications)
        db.flush()
        notification_ids = [item.id for item in notifications]
        db.commit()
    finally:
        db.close()

    try:
        token = login(calendar_setup["test_teacher_email"])
        response = client.get(
            "/api/v1/notifications/planning",
            headers=auth_headers(token),
        )

        assert response.status_code == 200, response.text
        results = response.json()

        assert any(
            item["message"] == "Test notification for current recipient"
            for item in results
        )
        assert not any(
            item["message"] == "Test notification for another recipient"
            for item in results
        )
    finally:
        cleanup = SessionLocal()
        try:
            cleanup.query(PlanningNotification).filter(
                PlanningNotification.id.in_(notification_ids)
            ).delete(synchronize_session=False)
            cleanup.commit()
        finally:
            cleanup.close()
