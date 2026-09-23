from datetime import datetime
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


def test_list_teaching_sessions_requires_authentication():
    """
    Teaching session listing must require authentication.
    """

    response = client.get("/api/v1/sessions")

    assert response.status_code == 401


def test_para_teacher_can_list_sessions_from_assigned_school():
    """
    A Para-Teacher can list sessions belonging to their
    assigned school.
    """
    token = login(
        PARA_TEACHERS["PT001"]["email"]
    )

    class_division = get_first_class_division(token)

    create_response = client.post(
        "/api/v1/sessions",
        headers=auth_headers(token),
        json={
            "class_division_id": class_division["id"],
            "session_date": "2026-09-23",
        },
    )

    assert create_response.status_code == 201

    response = client.get(
        "/api/v1/sessions",
        headers=auth_headers(token),
    )

    assert response.status_code == 200, response.text

    sessions = response.json()

    assert sessions

    authorized_divisions_response = client.get(
        "/api/v1/class-divisions",
        headers=auth_headers(token),
    )

    assert authorized_divisions_response.status_code == 200

    authorized_division_ids = {
        division["id"]
        for division in authorized_divisions_response.json()
    }

    assert authorized_division_ids

    assert all(
        session["class_division_id"]
        in authorized_division_ids
        for session in sessions
    )

def test_para_teacher_cannot_list_another_school_sessions():
    """
    PT001 must not see sessions belonging to PT002's school.
    """

    pt001_token = login(
        PARA_TEACHERS["PT001"]["email"]
    )

    pt002_token = login(
        PARA_TEACHERS["PT002"]["email"]
    )

    pt002_division = get_first_class_division(
        pt002_token
    )

    create_response = client.post(
        "/api/v1/sessions",
        headers=auth_headers(pt002_token),
        json={
            "class_division_id": pt002_division["id"],
            "session_date": "2026-09-23",
        },
    )

    assert create_response.status_code == 201

    response = client.get(
        "/api/v1/sessions",
        headers=auth_headers(pt001_token),
    )

    assert response.status_code == 200, response.text

    sessions = response.json()

    assert all(
        session["class_division_id"]
        != pt002_division["id"]
        for session in sessions
    )


def test_data_manager_can_list_project_sessions():
    """
    Data Manager has project-wide session.view access.
    """

    token = login(DATA_MANAGER)

    response = client.get(
        "/api/v1/sessions",
        headers=auth_headers(token),
    )

    assert response.status_code == 200, response.text

    assert isinstance(response.json(), list)


def test_list_sessions_can_filter_by_status():
    """
    The session list can be filtered by status.
    """

    token = login(
        PARA_TEACHERS["PT001"]["email"]
    )

    response = client.get(
        "/api/v1/sessions",
        headers=auth_headers(token),
        params={
            "status_filter": "PLANNED",
        },
    )

    assert response.status_code == 200, response.text

    sessions = response.json()

    assert all(
        session["status"] == "PLANNED"
        for session in sessions
    )


def test_list_sessions_can_filter_by_date():
    """
    The session list can be filtered by session date.
    """

    token = login(
        PARA_TEACHERS["PT001"]["email"]
    )

    response = client.get(
        "/api/v1/sessions",
        headers=auth_headers(token),
        params={
            "session_date": "2026-09-22",
        },
    )

    assert response.status_code == 200, response.text

    sessions = response.json()

    assert all(
        session["session_date"] == "2026-09-22"
        for session in sessions
    )


def test_list_sessions_can_filter_by_class_division():
    """
    The session list can be filtered by class division.
    """

    token = login(
        PARA_TEACHERS["PT001"]["email"]
    )

    class_division = get_first_class_division(token)

    response = client.get(
        "/api/v1/sessions",
        headers=auth_headers(token),
        params={
            "class_division_id": class_division["id"],
        },
    )

    assert response.status_code == 200, response.text

    sessions = response.json()

    assert all(
        session["class_division_id"]
        == class_division["id"]
        for session in sessions
    )


def test_list_sessions_returns_empty_list_for_no_matching_filter():
    """
    A valid query with no matching sessions returns an empty list.
    """

    token = login(
        PARA_TEACHERS["PT001"]["email"]
    )

    response = client.get(
        "/api/v1/sessions",
        headers=auth_headers(token),
        params={
            "session_date": "2099-01-01",
        },
    )

    assert response.status_code == 200

    assert response.json() == []


def test_get_teaching_session_requires_authentication():
    """
    Getting a teaching session must require authentication.
    """

    response = client.get(
        "/api/v1/sessions/"
        "00000000-0000-0000-0000-000000000000"
    )

    assert response.status_code == 401


def test_para_teacher_can_get_session_from_assigned_school():
    """
    A Para-Teacher can retrieve a session belonging to
    their assigned school.
    """

    token = login(
        PARA_TEACHERS["PT001"]["email"]
    )

    class_division = get_first_class_division(token)

    create_response = client.post(
        "/api/v1/sessions",
        headers=auth_headers(token),
        json={
            "class_division_id": class_division["id"],
            "session_date": "2026-09-24",
        },
    )

    assert create_response.status_code == 201

    created_session = create_response.json()

    response = client.get(
        f"/api/v1/sessions/{created_session['id']}",
        headers=auth_headers(token),
    )

    assert response.status_code == 200, response.text

    data = response.json()

    assert data["id"] == created_session["id"]
    assert data["class_division_id"] == class_division["id"]
    assert data["session_date"] == "2026-09-24"
    assert data["status"] == "PLANNED"


def test_para_teacher_cannot_get_session_from_another_school():
    """
    PT001 must not retrieve a session belonging to PT002's school.
    """

    pt001_token = login(
        PARA_TEACHERS["PT001"]["email"]
    )

    pt002_token = login(
        PARA_TEACHERS["PT002"]["email"]
    )

    pt002_division = get_first_class_division(
        pt002_token
    )

    create_response = client.post(
        "/api/v1/sessions",
        headers=auth_headers(pt002_token),
        json={
            "class_division_id": pt002_division["id"],
            "session_date": "2026-09-24",
        },
    )

    assert create_response.status_code == 201

    session_id = create_response.json()["id"]

    response = client.get(
        f"/api/v1/sessions/{session_id}",
        headers=auth_headers(pt001_token),
    )

    assert response.status_code == 403

    assert response.json()["detail"] == (
        "You are not authorized to access this school."
    )


def test_nonexistent_teaching_session_returns_not_found():
    """
    A non-existent teaching session returns 404.
    """

    token = login(
        PARA_TEACHERS["PT001"]["email"]
    )

    response = client.get(
        "/api/v1/sessions/"
        "00000000-0000-0000-0000-000000000000",
        headers=auth_headers(token),
    )

    assert response.status_code == 404

    assert response.json()["detail"] == (
        "Teaching session not found."
    )


def test_data_manager_can_get_project_session():
    """
    Data Manager has project-wide session.view access.
    """

    para_teacher_token = login(
        PARA_TEACHERS["PT001"]["email"]
    )

    class_division = get_first_class_division(
        para_teacher_token
    )

    create_response = client.post(
        "/api/v1/sessions",
        headers=auth_headers(para_teacher_token),
        json={
            "class_division_id": class_division["id"],
            "session_date": "2026-09-24",
        },
    )

    assert create_response.status_code == 201

    session_id = create_response.json()["id"]

    data_manager_token = login(DATA_MANAGER)

    response = client.get(
        f"/api/v1/sessions/{session_id}",
        headers=auth_headers(data_manager_token),
    )

    assert response.status_code == 200, response.text

    data = response.json()

    assert data["id"] == session_id


def test_start_teaching_session_requires_authentication():
    """
    Starting a teaching session requires authentication.
    """

    response = client.post(
        "/api/v1/sessions/"
        "00000000-0000-0000-0000-000000000000/start"
    )

    assert response.status_code == 401

def test_para_teacher_can_start_planned_session():
    """
    A Para-Teacher can start a planned session
    in their assigned school.
    """

    token = login(
        PARA_TEACHERS["PT001"]["email"]
    )

    class_division = get_first_class_division(token)

    create_response = client.post(
        "/api/v1/sessions",
        headers=auth_headers(token),
        json={
            "class_division_id": class_division["id"],
            "session_date": "2026-09-25",
        },
    )

    assert create_response.status_code == 201

    session_id = create_response.json()["id"]

    response = client.post(
        f"/api/v1/sessions/{session_id}/start",
        headers=auth_headers(token),
    )

    assert response.status_code == 200, response.text

    data = response.json()

    assert data["id"] == session_id
    assert data["status"] == "IN_PROGRESS"
    assert data["actual_start_time"] is not None
    assert data["actual_end_time"] is None
    assert data["duration_minutes"] is None


def test_start_session_records_actual_start_time():
    """
    Starting a session records an actual start timestamp.
    """

    token = login(
        PARA_TEACHERS["PT001"]["email"]
    )

    class_division = get_first_class_division(token)

    create_response = client.post(
        "/api/v1/sessions",
        headers=auth_headers(token),
        json={
            "class_division_id": class_division["id"],
            "session_date": "2026-09-25",
        },
    )

    assert create_response.status_code == 201

    session_id = create_response.json()["id"]

    response = client.post(
        f"/api/v1/sessions/{session_id}/start",
        headers=auth_headers(token),
    )

    assert response.status_code == 200

    actual_start_time = response.json()["actual_start_time"]

    parsed = datetime.fromisoformat(
        actual_start_time.replace("Z", "+00:00")
    )

    assert parsed.tzinfo is not None



def test_cannot_start_already_started_session():
    """
    An IN_PROGRESS session cannot be started again.
    """

    token = login(
        PARA_TEACHERS["PT001"]["email"]
    )

    class_division = get_first_class_division(token)

    create_response = client.post(
        "/api/v1/sessions",
        headers=auth_headers(token),
        json={
            "class_division_id": class_division["id"],
            "session_date": "2026-09-25",
        },
    )

    assert create_response.status_code == 201

    session_id = create_response.json()["id"]

    first_response = client.post(
        f"/api/v1/sessions/{session_id}/start",
        headers=auth_headers(token),
    )

    assert first_response.status_code == 200

    second_response = client.post(
        f"/api/v1/sessions/{session_id}/start",
        headers=auth_headers(token),
    )

    assert second_response.status_code == 409

    assert second_response.json()["detail"] == (
        "Only planned teaching sessions can be started."
    )



def test_para_teacher_cannot_start_session_from_another_school():
    """
    PT001 cannot start a session belonging to PT002's school.
    """

    pt001_token = login(
        PARA_TEACHERS["PT001"]["email"]
    )

    pt002_token = login(
        PARA_TEACHERS["PT002"]["email"]
    )

    pt002_division = get_first_class_division(
        pt002_token
    )

    create_response = client.post(
        "/api/v1/sessions",
        headers=auth_headers(pt002_token),
        json={
            "class_division_id": pt002_division["id"],
            "session_date": "2026-09-25",
        },
    )

    assert create_response.status_code == 201

    session_id = create_response.json()["id"]

    response = client.post(
        f"/api/v1/sessions/{session_id}/start",
        headers=auth_headers(pt001_token),
    )

    assert response.status_code == 403

    assert response.json()["detail"] == (
        "You are not authorized to access this school."
    )


def test_start_nonexistent_session_returns_not_found():
    """
    Starting a non-existent session returns 404.
    """

    token = login(
        PARA_TEACHERS["PT001"]["email"]
    )

    response = client.post(
        "/api/v1/sessions/"
        "00000000-0000-0000-0000-000000000000/start",
        headers=auth_headers(token),
    )

    assert response.status_code == 404

    assert response.json()["detail"] == (
        "Teaching session not found."
    )

def test_complete_teaching_session_requires_authentication():
    """
    Completing a teaching session requires authentication.
    """

    response = client.post(
        "/api/v1/sessions/"
        "00000000-0000-0000-0000-000000000000/complete"
    )

    assert response.status_code == 401


def test_para_teacher_can_complete_in_progress_session():
    """
    A Para-Teacher can complete an in-progress session
    in their assigned school.
    """

    token = login(
        PARA_TEACHERS["PT001"]["email"]
    )

    class_division = get_first_class_division(token)

    create_response = client.post(
        "/api/v1/sessions",
        headers=auth_headers(token),
        json={
            "class_division_id": class_division["id"],
            "session_date": "2026-09-25",
        },
    )

    assert create_response.status_code == 201

    session_id = create_response.json()["id"]

    start_response = client.post(
        f"/api/v1/sessions/{session_id}/start",
        headers=auth_headers(token),
    )

    assert start_response.status_code == 200

    response = client.post(
        f"/api/v1/sessions/{session_id}/complete",
        headers=auth_headers(token),
    )

    assert response.status_code == 200, response.text

    data = response.json()

    assert data["id"] == session_id
    assert data["status"] == "COMPLETED"
    assert data["actual_start_time"] is not None
    assert data["actual_end_time"] is not None
    assert data["duration_minutes"] is not None
    assert data["duration_minutes"] >= 0


def test_complete_session_records_actual_end_time():
    """
    Completing a session records an actual UTC end timestamp.
    """

    token = login(
        PARA_TEACHERS["PT001"]["email"]
    )

    class_division = get_first_class_division(token)

    create_response = client.post(
        "/api/v1/sessions",
        headers=auth_headers(token),
        json={
            "class_division_id": class_division["id"],
            "session_date": "2026-09-25",
        },
    )

    assert create_response.status_code == 201

    session_id = create_response.json()["id"]

    start_response = client.post(
        f"/api/v1/sessions/{session_id}/start",
        headers=auth_headers(token),
    )

    assert start_response.status_code == 200

    response = client.post(
        f"/api/v1/sessions/{session_id}/complete",
        headers=auth_headers(token),
    )

    assert response.status_code == 200

    actual_end_time = response.json()["actual_end_time"]

    parsed = datetime.fromisoformat(
        actual_end_time.replace("Z", "+00:00")
    )

    assert parsed.tzinfo is not None


def test_complete_session_calculates_duration():
    """
    Completing a session calculates duration from the
    server-controlled start and end timestamps.
    """

    token = login(
        PARA_TEACHERS["PT001"]["email"]
    )

    class_division = get_first_class_division(token)

    create_response = client.post(
        "/api/v1/sessions",
        headers=auth_headers(token),
        json={
            "class_division_id": class_division["id"],
            "session_date": "2026-09-25",
        },
    )

    assert create_response.status_code == 201

    session_id = create_response.json()["id"]

    start_response = client.post(
        f"/api/v1/sessions/{session_id}/start",
        headers=auth_headers(token),
    )

    assert start_response.status_code == 200

    response = client.post(
        f"/api/v1/sessions/{session_id}/complete",
        headers=auth_headers(token),
    )

    assert response.status_code == 200

    data = response.json()

    assert data["actual_start_time"] is not None
    assert data["actual_end_time"] is not None
    assert data["duration_minutes"] >= 0


def test_cannot_complete_planned_session():
    """
    A planned session cannot be completed directly.
    """

    token = login(
        PARA_TEACHERS["PT001"]["email"]
    )

    class_division = get_first_class_division(token)

    create_response = client.post(
        "/api/v1/sessions",
        headers=auth_headers(token),
        json={
            "class_division_id": class_division["id"],
            "session_date": "2026-09-25",
        },
    )

    assert create_response.status_code == 201

    session_id = create_response.json()["id"]

    response = client.post(
        f"/api/v1/sessions/{session_id}/complete",
        headers=auth_headers(token),
    )

    assert response.status_code == 409

    assert response.json()["detail"] == (
        "Only in-progress teaching sessions "
        "can be completed."
    )


def test_cannot_complete_already_completed_session():
    """
    A completed session cannot be completed again.
    """

    token = login(
        PARA_TEACHERS["PT001"]["email"]
    )

    class_division = get_first_class_division(token)

    create_response = client.post(
        "/api/v1/sessions",
        headers=auth_headers(token),
        json={
            "class_division_id": class_division["id"],
            "session_date": "2026-09-25",
        },
    )

    assert create_response.status_code == 201

    session_id = create_response.json()["id"]

    start_response = client.post(
        f"/api/v1/sessions/{session_id}/start",
        headers=auth_headers(token),
    )

    assert start_response.status_code == 200

    first_response = client.post(
        f"/api/v1/sessions/{session_id}/complete",
        headers=auth_headers(token),
    )

    assert first_response.status_code == 200

    second_response = client.post(
        f"/api/v1/sessions/{session_id}/complete",
        headers=auth_headers(token),
    )

    assert second_response.status_code == 409

    assert second_response.json()["detail"] == (
        "Only in-progress teaching sessions "
        "can be completed."
    )


def test_para_teacher_cannot_complete_session_from_another_school():
    """
    PT001 cannot complete a session belonging to PT002's school.
    """

    pt001_token = login(
        PARA_TEACHERS["PT001"]["email"]
    )

    pt002_token = login(
        PARA_TEACHERS["PT002"]["email"]
    )

    pt002_division = get_first_class_division(
        pt002_token
    )

    create_response = client.post(
        "/api/v1/sessions",
        headers=auth_headers(pt002_token),
        json={
            "class_division_id": pt002_division["id"],
            "session_date": "2026-09-25",
        },
    )

    assert create_response.status_code == 201

    session_id = create_response.json()["id"]

    start_response = client.post(
        f"/api/v1/sessions/{session_id}/start",
        headers=auth_headers(pt002_token),
    )

    assert start_response.status_code == 200

    response = client.post(
        f"/api/v1/sessions/{session_id}/complete",
        headers=auth_headers(pt001_token),
    )

    assert response.status_code == 403

    assert response.json()["detail"] == (
        "You are not authorized to access this school."
    )


def test_complete_nonexistent_session_returns_not_found():
    """
    Completing a non-existent session returns 404.
    """

    token = login(
        PARA_TEACHERS["PT001"]["email"]
    )

    response = client.post(
        "/api/v1/sessions/"
        "00000000-0000-0000-0000-000000000000/complete",
        headers=auth_headers(token),
    )

    assert response.status_code == 404

    assert response.json()["detail"] == (
        "Teaching session not found."
    )
