import os

import pytest
from app.database import SessionLocal
from app.models import User
from dotenv import load_dotenv
from fastapi.testclient import TestClient

from app.main import app

load_dotenv()

DEMO_PASSWORD = os.getenv("DEMO_USER_PASSWORD")

if not DEMO_PASSWORD:
    raise RuntimeError(
        "DEMO_USER_PASSWORD must be configured in .env "
        "before running teaching session CRUD tests."
    )


client = TestClient(app)


PARA_TEACHERS = {
    "PT001": {
        "email": "pt001@demo.vigyan.com",
        "school_code": "PVS",
    },
    "PT002": {
        "email": "pt002@demo.vigyan.com",
        "school_code": "NLS",
    },
    "PT003": {
        "email": "pt003@demo.vigyan.com",
        "school_code": "SHY",
    },
    "PT004": {
        "email": "pt004@demo.vigyan.com",
        "school_code": "UECL",
    },
}


DATA_MANAGER = "dm001@demo.vigyan.com"


def login(email: str) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": email,
            "password": DEMO_PASSWORD,
        },
    )

    assert response.status_code == 200, response.text

    return response.json()["session_token"]


def auth_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
    }

def get_user_id_by_email(email: str):
    db = SessionLocal()

    try:
        user = (
            db.query(User)
            .filter(User.email == email)
            .first()
        )

        assert user is not None

        return str(user.id)

    finally:
        db.close()

def get_first_class_division(token: str) -> dict:
    response = client.get(
        "/api/v1/class-divisions",
        headers=auth_headers(token),
    )

    assert response.status_code == 200, response.text

    divisions = response.json()

    assert divisions

    return divisions[0]


def test_create_teaching_session_requires_authentication():
    """
    Teaching session creation must require authentication.
    """

    response = client.post(
        "/api/v1/sessions",
        json={
            "class_division_id": "00000000-0000-0000-0000-000000000000",
            "session_date": "2026-09-21",
        },
    )

    assert response.status_code == 401


@pytest.mark.parametrize(
    "user_code",
    ["PT001", "PT002", "PT003", "PT004"],
)
def test_para_teacher_can_create_teaching_session(user_code):
    """
    A Para-Teacher can create a planned teaching session
    for a class division in their assigned school.
    """

    user = PARA_TEACHERS[user_code]

    token = login(user["email"])

    class_division = get_first_class_division(token)

    response = client.post(
        "/api/v1/sessions",
        headers=auth_headers(token),
        json={
            "class_division_id": class_division["id"],
            "session_date": "2026-09-21",
            "planned_start_time": "09:00:00",
            "planned_end_time": "10:00:00",
            "remarks": "  Planned teaching session  ",
        },
    )

    assert response.status_code == 201, response.text

    data = response.json()

    assert data["class_division_id"] == class_division["id"]
    assert data["session_date"] == "2026-09-21"
    assert data["planned_start_time"] == "09:00:00"
    assert data["planned_end_time"] == "10:00:00"
    assert data["status"] == "PLANNED"
    assert data["remarks"] == "Planned teaching session"
    assert data["feedback_submitted"] is False
    assert data["submitted_at"] is None
    assert data["actual_start_time"] is None
    assert data["actual_end_time"] is None
    assert data["duration_minutes"] is None
    assert data["data_origin"] == "PRODUCTION"


@pytest.mark.parametrize(
    "user_code",
    ["PT001", "PT002", "PT003", "PT004"],
)
def test_para_teacher_session_is_assigned_to_authenticated_user(user_code):
    """
    The para_teacher_id must always come from the authenticated user.

    A client must not be able to assign a session to another
    para-teacher.
    """

    user = PARA_TEACHERS[user_code]

    token = login(user["email"])

    class_division = get_first_class_division(token)

    response = client.post(
        "/api/v1/sessions",
        headers=auth_headers(token),
        json={
            "class_division_id": class_division["id"],
            "session_date": "2026-09-22",
            "para_teacher_id": "00000000-0000-0000-0000-000000000001",
        },
    )

    assert response.status_code == 201, response.text

    data = response.json()

    # The endpoint must ignore the client-supplied para_teacher_id.
    authenticated_user_id = get_user_id_by_email(
        user["email"]
    )

    assert data["para_teacher_id"] == authenticated_user_id


def test_para_teacher_cannot_create_session_for_another_school():
    """
    PT001 must not create a session against a class division
    belonging to PT002's school.
    """

    pt001_token = login(
        PARA_TEACHERS["PT001"]["email"]
    )

    pt002_token = login(
        PARA_TEACHERS["PT002"]["email"]
    )

    nls_division = get_first_class_division(pt002_token)

    response = client.post(
        "/api/v1/sessions",
        headers=auth_headers(pt001_token),
        json={
            "class_division_id": nls_division["id"],
            "session_date": "2026-09-22",
        },
    )

    assert response.status_code == 403

    assert response.json()["detail"] == (
        "You are not authorized to access this school."
    )


def test_nonexistent_class_division_returns_not_found():
    """
    A session cannot be created for a class division that does not exist.
    """

    token = login(
        PARA_TEACHERS["PT001"]["email"]
    )

    response = client.post(
        "/api/v1/sessions",
        headers=auth_headers(token),
        json={
            "class_division_id": (
                "00000000-0000-0000-0000-000000000000"
            ),
            "session_date": "2026-09-22",
        },
    )

    assert response.status_code == 404

    assert response.json()["detail"] == (
        "Class division not found."
    )


def test_data_manager_can_create_teaching_session():
    """
    Data Manager currently has session.create permission,
    so this test documents the current permission design.

    This is intentionally expected to succeed.
    """

    token = login(DATA_MANAGER)

    class_division = get_first_class_division(token)

    response = client.post(
        "/api/v1/sessions",
        headers=auth_headers(token),
        json={
            "class_division_id": class_division["id"],
            "session_date": "2026-09-22",
        },
    )

    assert response.status_code == 201, response.text


def test_management_cannot_create_teaching_session():
    """
    Management has session.view but not session.create.
    """

    # Management demo user is not currently seeded in the project.
    # This test is therefore intentionally omitted until a management
    # demo account is available.
    pytest.skip(
        "Management demo user is not currently seeded."
    )


def test_stem_coordinator_cannot_create_teaching_session():
    """
    STEM Coordinator has session.view but not session.create.
    """

    # STEM Coordinator demo user is not currently seeded in the project.
    # This test is therefore intentionally omitted until a coordinator
    # demo account is available.
    pytest.skip(
        "STEM Coordinator demo user is not currently seeded."
    )


@pytest.mark.parametrize(
    "payload",
    [
        {
            "planned_start_time": "09:00:00",
        },
        {
            "planned_end_time": "10:00:00",
        },
        {
            "planned_start_time": "10:00:00",
            "planned_end_time": "09:00:00",
        },
        {
            "planned_start_time": "09:00:00",
            "planned_end_time": "09:00:00",
        },
    ],
)
def test_invalid_planned_time_range_is_rejected(payload):
    """
    Planned start/end times must be supplied as a valid pair,
    with end time later than start time.
    """

    token = login(
        PARA_TEACHERS["PT001"]["email"]
    )

    class_division = get_first_class_division(token)

    request_payload = {
        "class_division_id": class_division["id"],
        "session_date": "2026-09-22",
        **payload,
    }

    response = client.post(
        "/api/v1/sessions",
        headers=auth_headers(token),
        json=request_payload,
    )

    assert response.status_code == 422


def test_client_cannot_control_data_origin():
    """
    data_origin is not accepted as an API input field.

    The server must always create production records through
    this endpoint.
    """

    token = login(
        PARA_TEACHERS["PT001"]["email"]
    )

    class_division = get_first_class_division(token)

    response = client.post(
        "/api/v1/sessions",
        headers=auth_headers(token),
        json={
            "class_division_id": class_division["id"],
            "session_date": "2026-09-22",
            "data_origin": "DEMO",
        },
    )

    assert response.status_code == 201, response.text

    data = response.json()

    assert data["data_origin"] == "PRODUCTION"


def test_remarks_are_trimmed():
    """
    Leading and trailing whitespace in remarks is removed.
    """

    token = login(
        PARA_TEACHERS["PT001"]["email"]
    )

    class_division = get_first_class_division(token)

    response = client.post(
        "/api/v1/sessions",
        headers=auth_headers(token),
        json={
            "class_division_id": class_division["id"],
            "session_date": "2026-09-22",
            "remarks": "   Session remarks   ",
        },
    )

    assert response.status_code == 201, response.text

    assert response.json()["remarks"] == "Session remarks"
