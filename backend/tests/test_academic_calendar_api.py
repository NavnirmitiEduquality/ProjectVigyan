from __future__ import annotations

import os
from datetime import date, time, timedelta
from uuid import UUID, uuid4
from unittest.mock import MagicMock, patch

import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient

from app.database import SessionLocal, get_db
from app.main import app
from app.models import (
    AuthSession,
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


@pytest.fixture
def academic_years_list_setup():
    db = SessionLocal()
    suffix = uuid4().hex
    years = [
        AcademicYear(
            name=f"Years-List-Active-{suffix}",
            start_date=date(2025, 4, 1),
            end_date=date(2026, 3, 31),
            is_active=True,
            data_origin="PRODUCTION",
        ),
        AcademicYear(
            name=f"Years-List-Recent-{suffix}",
            start_date=date(2026, 4, 1),
            end_date=date(2027, 3, 31),
            is_active=False,
            data_origin="PRODUCTION",
        ),
        AcademicYear(
            name=f"Years-List-Older-{suffix}",
            start_date=date(2024, 4, 1),
            end_date=date(2025, 3, 31),
            is_active=False,
            data_origin="PRODUCTION",
        ),
        AcademicYear(
            name=f"Years-List-Demo-{suffix}",
            start_date=date(2027, 4, 1),
            end_date=date(2028, 3, 31),
            is_active=True,
            data_origin="DEMO",
        ),
        AcademicYear(
            name=f"Years-List-Test-{suffix}",
            start_date=date(2028, 4, 1),
            end_date=date(2029, 3, 31),
            is_active=True,
            data_origin="TEST",
        ),
    ]

    user = None
    try:
        db.add_all(years)

        password_hash = (
            db.query(User.password_hash)
            .filter(User.email == PARA_TEACHER_EMAIL)
            .scalar()
        )
        assert password_hash is not None

        user = User(
            user_code=f"YEARS-LIST-{suffix[:12]}",
            full_name="Academic Year List API Test User",
            email=f"years-list-{suffix}@example.com",
            password_hash=password_hash,
            status="ACTIVE",
            data_origin="TEST",
        )
        db.add(user)
        db.commit()

        result = {
            "year_ids": [year.id for year in years],
            "production_ids": {
                years[0].id,
                years[1].id,
                years[2].id,
            },
            "expected_order": [
                years[0].id,
                years[1].id,
                years[2].id,
            ],
            "user_id": user.id,
            "user_email": user.email,
        }
        yield result
    finally:
        if user is not None:
            db.query(AuthSession).filter(
                AuthSession.user_id == user.id
            ).delete(synchronize_session=False)

        db.query(AcademicYear).filter(
            AcademicYear.id.in_([year.id for year in years])
        ).delete(synchronize_session=False)
        if user is not None:
            db.query(User).filter(User.id == user.id).delete(
                synchronize_session=False
            )
        db.commit()
        db.close()


def test_auth_me_returns_effective_calendar_permissions(calendar_setup):
    cases = [
        (calendar_setup["admin_email"], True),
        (calendar_setup["data_manager_email"], True),
        (
            calendar_setup["cross_teacher_role_emails"]["MANAGEMENT"],
            False,
        ),
        (calendar_setup["test_teacher_email"], False),
    ]

    for email, can_manage_calendar in cases:
        token = login(email)
        response = client.get(
            "/api/v1/auth/me",
            headers=auth_headers(token),
        )

        assert response.status_code == 200, response.text

        result = response.json()

        assert result["email"] == email
        assert result["status"] == "ACTIVE"
        assert result["user_id"]
        assert result["user_code"]
        assert result["full_name"]

        permissions = result["permissions"]
        assert isinstance(permissions, list)
        assert "calendar.view" in permissions

        assert ("calendar.manage" in permissions) is can_manage_calendar


def test_list_academic_years_requires_authentication():
    response = client.get("/api/v1/academic-calendar/years")
    assert response.status_code == 401


def test_list_academic_years_filters_and_orders_production_years(
    academic_years_list_setup,
):
    token = login(PARA_TEACHER_EMAIL)
    response = client.get(
        "/api/v1/academic-calendar/years",
        headers=auth_headers(token),
    )

    assert response.status_code == 200, response.text
    results = response.json()

    returned_ids = [UUID(item["id"]) for item in results]
    returned_test_ids = set(returned_ids) & set(
        academic_years_list_setup["year_ids"]
    )

    assert returned_test_ids == academic_years_list_setup["production_ids"]

    returned_fixture_ids = [
        year_id
        for year_id in returned_ids
        if year_id in academic_years_list_setup["production_ids"]
    ]
    assert returned_fixture_ids == academic_years_list_setup["expected_order"]

    fixture_results = {
        UUID(item["id"]): item
        for item in results
        if UUID(item["id"]) in academic_years_list_setup["production_ids"]
    }
    for year_id, item in fixture_results.items():
        assert set(item) == {
            "id",
            "name",
            "start_date",
            "end_date",
            "is_active",
        }
        assert item["start_date"]
        assert item["end_date"]


def test_list_academic_years_requires_calendar_view_permission(
    academic_years_list_setup,
):
    token = login(academic_years_list_setup["user_email"])

    response = client.get(
        "/api/v1/academic-calendar/years",
        headers=auth_headers(token),
    )

    assert response.status_code == 403, response.text


def test_list_academic_years_returns_empty_list_when_no_production_years():
    from app.dependencies import get_current_user

    db = MagicMock()
    query = db.query.return_value
    query.filter.return_value = query
    query.order_by.return_value = query
    query.all.return_value = []

    test_user = MagicMock(spec=User)

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: test_user

    try:
        response = client.get(
            "/api/v1/academic-calendar/years",
            headers={"Authorization": "Bearer empty-years-test-token"},
        )

        assert response.status_code == 200, response.text
        assert response.json() == []
        query.all.assert_called_once_with()
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)


def test_data_manager_can_create_production_academic_year(calendar_setup):
    token = login(calendar_setup["data_manager_email"])
    name = f"API-Created-{uuid4()}"

    response = client.post(
        "/api/v1/academic-calendar/years",
        headers=auth_headers(token),
        json={
            "name": name,
            "start_date": "2028-04-01",
            "end_date": "2029-03-31",
            "is_active": False,
        },
    )

    assert response.status_code == 201, response.text

    result = response.json()
    assert result["name"] == name
    assert result["start_date"] == "2028-04-01"
    assert result["end_date"] == "2029-03-31"
    assert result["is_active"] is False

    db = SessionLocal()
    try:
        created_year = (
            db.query(AcademicYear)
            .filter(AcademicYear.id == UUID(result["id"]))
            .one()
        )
        assert created_year.data_origin == "PRODUCTION"
    finally:
        db.close()

    listed = client.get(
        "/api/v1/academic-calendar/years",
        headers=auth_headers(token),
    )
    assert listed.status_code == 200, listed.text
    assert any(item["id"] == result["id"] for item in listed.json())
    cleanup = SessionLocal()
    try:
        cleanup.query(AcademicYear).filter(
            AcademicYear.id == UUID(result["id"])
        ).delete(synchronize_session=False)
        cleanup.commit()
    finally:
        cleanup.close()


def test_para_teacher_cannot_create_academic_year(calendar_setup):
    token = login(calendar_setup["test_teacher_email"])

    response = client.post(
        "/api/v1/academic-calendar/years",
        headers=auth_headers(token),
        json={
            "name": f"Unauthorized-{uuid4()}",
            "start_date": "2028-04-01",
            "end_date": "2029-03-31",
        },
    )

    assert response.status_code == 403, response.text


def test_create_academic_year_rejects_duplicate_name(calendar_setup):
    token = login(calendar_setup["data_manager_email"])

    db = SessionLocal()
    try:
        existing_year = (
            db.query(AcademicYear)
            .filter(AcademicYear.id == calendar_setup["year_id"])
            .one()
        )
        duplicate_name = existing_year.name
    finally:
        db.close()

    response = client.post(
        "/api/v1/academic-calendar/years",
        headers=auth_headers(token),
        json={
            "name": duplicate_name,
            "start_date": "2028-04-01",
            "end_date": "2029-03-31",
        },
    )

    assert response.status_code == 409, response.text


def test_create_academic_year_rejects_invalid_date_range(calendar_setup):
    token = login(calendar_setup["data_manager_email"])

    response = client.post(
        "/api/v1/academic-calendar/years",
        headers=auth_headers(token),
        json={
            "name": f"Invalid-Dates-{uuid4()}",
            "start_date": "2029-03-31",
            "end_date": "2028-04-01",
        },
    )

    assert response.status_code == 422, response.text
