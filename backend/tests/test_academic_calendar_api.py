from __future__ import annotations

import os
from datetime import date, time, timedelta
from uuid import UUID, uuid4

import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models import (
    AcademicHoliday,
    AcademicYear,
    ClassDivision,
    SessionPlanItem,
    SessionPlanWeek,
    Role,
    User,
    UserAssignment,
    UserRole,
)
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
        data_origin="TEST",
    )
    db.add(year)
    db.flush()

    teacher_id = user_id(PARA_TEACHER_EMAIL)
    teacher = db.query(User).filter(User.id == teacher_id).one()
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
    db.add(
        UserRole(
            user_id=admin.id,
            role_id=db.query(Role)
            .filter(Role.code == "PLATFORM_OWNER")
            .one()
            .id,
            is_active=True,
        )
    )
    db.flush()
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
    while (
        db.query(SessionPlanWeek)
        .filter(
            SessionPlanWeek.para_teacher_id == teacher_id,
            SessionPlanWeek.week_start_date == week_start,
        )
        .first()
        is not None
    ):
        week_start += timedelta(days=7)

    service = SessionPlanService()
    week = service.get_or_create_week(
        db,
        para_teacher_id=teacher_id,
        week_start_date=week_start,
        data_origin="TEST",
    )
    item = service.create_item(
        db,
        para_teacher_id=teacher_id,
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
        "admin_email": admin_email,
        "item_id": item.id,
        "week_start": week_start,
        "holiday_ids": [],
    }
    db.close()

    yield result

    cleanup = SessionLocal()
    try:
        cleanup.query(AcademicHoliday).filter(
            AcademicHoliday.academic_year_id == result["year_id"]
        ).delete(synchronize_session=False)
        cleanup.query(AcademicYear).filter(
            AcademicYear.id == result["year_id"]
        ).delete(synchronize_session=False)
        cleanup.query(SessionPlanItem).filter(
            SessionPlanItem.id == result["item_id"]
        ).delete(synchronize_session=False)
        cleanup.query(User).filter(
            User.email == result["admin_email"]
        ).delete(synchronize_session=False)
        cleanup.commit()
    finally:
        cleanup.close()


def test_calendar_requires_authentication(calendar_setup):
    response = client.get(
        "/api/v1/academic-calendar",
        params={
            "start_date": "2027-01-01",
            "end_date": "2027-01-03",
        },
    )
    assert response.status_code == 401


def test_para_teacher_can_view_own_calendar(calendar_setup):
    token = login(PARA_TEACHER_EMAIL)
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


def test_data_manager_can_manage_holidays_and_list_them(calendar_setup):
    token = login(calendar_setup["admin_email"])
    holiday_date = (
        calendar_setup["week_start"] + timedelta(days=1)
    ).isoformat()

    created = client.post(
        "/api/v1/academic-calendar/holidays",
        headers=auth_headers(token),
        json={
            "holiday_date": holiday_date,
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
    token = login(PARA_TEACHER_EMAIL)
    response = client.patch(
        f"/api/v1/academic-calendar/sessions/"
        f"{calendar_setup['item_id']}/reschedule",
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
    token = login(PARA_TEACHER_EMAIL)
    response = client.patch(
        f"/api/v1/academic-calendar/sessions/"
        f"{calendar_setup['item_id']}/reschedule",
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
        f"/api/v1/academic-calendar/compliance/"
        f"{calendar_setup['week_start'].isoformat()}",
        headers=auth_headers(token),
    )

    assert response.status_code == 200, response.text
    matching = [
        row
        for row in response.json()
        if row["para_teacher_id"] == str(calendar_setup["teacher_id"])
    ]
    assert matching
    assert matching[0]["planned_session_count"] == 1
    assert matching[0]["minimum_met"] is False
