import os
import uuid
from datetime import date, datetime, timezone
import io

import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient
from sqlalchemy import func

from app.database import SessionLocal
from app.main import app
from app.models import (
    ClassDivision,
    SessionEngagement,
    Student,
    TeachingSession,
    TLM,
    User,
)

load_dotenv()

client = TestClient(app)

DEMO_PASSWORD = os.getenv("DEMO_USER_PASSWORD")

PT001_EMAIL = "pt001@demo.vigyan.com"
PT002_EMAIL = "pt002@demo.vigyan.com"
MANAGEMENT_EMAIL = "management@demo.vigyan.com"
STEM_EMAIL = "stem@demo.vigyan.com"
DATA_MANAGER_EMAIL = "dm001@demo.vigyan.com"
PLATFORM_OWNER_EMAIL = "infotech@navnirmitieduquality.org"


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


def auth_headers(email: str) -> dict:
    token = login(email)

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

        assert user is not None, f"User not found: {email}"

        return user.id
    finally:
        db.close()


def get_first_class_division(
    db,
    school_id=None,
):
    query = db.query(ClassDivision).order_by(
        ClassDivision.created_at
    )

    if school_id is not None:
        query = query.filter(
            ClassDivision.school_id == school_id
        )

    class_division = query.first()

    assert class_division is not None

    return class_division


def get_para_teacher_school_id(
    email: str,
):
    db = SessionLocal()

    try:
        user = (
            db.query(User)
            .filter(User.email == email)
            .first()
        )

        assert user is not None

        # Para-teacher assignments are used by the
        # authorization layer. Import here to keep the
        # helper consistent with the existing project.
        from app.models import UserAssignment

        assignment = (
            db.query(UserAssignment)
            .filter(
                UserAssignment.user_id == user.id,
                UserAssignment.is_active.is_(True),
                UserAssignment.scope_type == "SCHOOL",
            )
            .order_by(UserAssignment.start_date)
            .first()
        )

        assert assignment is not None

        return assignment.school_id

    finally:
        db.close()


def create_session(
    email: str = PT001_EMAIL,
):
    db = SessionLocal()

    try:
        school_id = get_para_teacher_school_id(email)

        class_division = get_first_class_division(
            db,
            school_id=school_id,
        )

        headers = auth_headers(email)

        response = client.post(
            "/api/v1/sessions",
            headers=headers,
            json={
                "class_division_id": str(
                    class_division.id
                ),
                "session_date": str(date.today()),
            },
        )

        assert response.status_code == 201, response.text

        return response.json()["id"]

    finally:
        db.close()


def start_session(
    session_id: str,
    email: str = PT001_EMAIL,
):
    response = client.post(
        f"/api/v1/sessions/{session_id}/start",
        headers=auth_headers(email),
    )

    assert response.status_code == 200, response.text

    return response.json()


def complete_session(
    session_id: str,
    email: str = PT001_EMAIL,
):
    response = client.post(
        f"/api/v1/sessions/{session_id}/complete",
        headers=auth_headers(email),
    )

    assert response.status_code == 200, response.text

    return response.json()


def get_engagement_count(
    session_id: str,
) -> int:
    db = SessionLocal()

    try:
        return (
            db.query(func.count(SessionEngagement.id))
            .filter(
                SessionEngagement.teaching_session_id
                == uuid.UUID(session_id)
            )
            .scalar()
        )
    finally:
        db.close()


def get_engagement_from_db(
    session_id: str,
):
    db = SessionLocal()

    try:
        return (
            db.query(SessionEngagement)
            .filter(
                SessionEngagement.teaching_session_id
                == uuid.UUID(session_id)
            )
            .first()
        )
    finally:
        db.close()


def prepare_session_for_completion_without_engagement(
    session_id: str,
    email: str,
) -> None:
    db = SessionLocal()

    try:
        session = (
            db.query(TeachingSession)
            .filter(TeachingSession.id == session_id)
            .first()
        )

        assert session is not None

        class_division_id = session.class_division_id

        students = (
            db.query(Student)
            .filter(
                Student.class_division_id == class_division_id,
                Student.status == "ACTIVE",
            )
            .order_by(Student.roll_no)
            .all()
        )

        assert students, (
            "Demo class division must contain active students."
        )

        active_tlm = (
            db.query(TLM)
            .filter(TLM.is_active.is_(True))
            .order_by(TLM.name)
            .first()
        )

        assert active_tlm is not None, (
            "Demo database must contain an active TLM."
        )

        tlm_id = str(active_tlm.id)

    finally:
        db.close()

    token = auth_headers(email)

    attendance_response = client.post(
        f"/api/v1/sessions/{session_id}/attendance",
        headers=token,
        json={
            "records": [
                {
                    "student_id": str(student.id),
                    "status": "PRESENT",
                }
                for student in students
            ]
        },
    )

    assert attendance_response.status_code == 200, (
        attendance_response.text
    )

    tlm_response = client.post(
        f"/api/v1/sessions/{session_id}/tlms",
        headers=token,
        data={
            "tlm_id": tlm_id,
            "quantity": "1",
            "usage": "Used for the activity.",
        },
    )

    assert tlm_response.status_code == 201, (
        tlm_response.text
    )

    from PIL import Image

    buffer = io.BytesIO()

    image = Image.new(
        "RGB",
        (100, 100),
        (255, 255, 255),
    )

    image.save(
        buffer,
        format="JPEG",
        quality=90,
    )

    evidence_response = client.post(
        f"/api/v1/sessions/{session_id}/evidence",
        headers=token,
        files={
            "photo": (
                "session-evidence.jpg",
                buffer.getvalue(),
                "image/jpeg",
            )
        },
        data={
            "captured_at": datetime.now(
                timezone.utc
            ).isoformat(),
            "latitude": "19.076000",
            "longitude": "72.877700",
        },
    )

    assert evidence_response.status_code == 201, (
        evidence_response.text
    )

    feedback_response = client.patch(
        f"/api/v1/sessions/{session_id}/feedback",
        headers=token,
        json={
            "remarks": "Session completed successfully.",
        },
    )

    assert feedback_response.status_code == 200, (
        feedback_response.text
    )


# ------------------------------------------------------------------
# Authentication
# ------------------------------------------------------------------


def test_get_engagement_requires_authentication():
    session_id = create_session()

    response = client.get(
        f"/api/v1/sessions/{session_id}/engagement"
    )

    assert response.status_code == 401


def test_post_engagement_requires_authentication():
    session_id = create_session()

    response = client.post(
        f"/api/v1/sessions/{session_id}/engagement",
        json={"score": 3},
    )

    assert response.status_code == 401


# ------------------------------------------------------------------
# Score validation
# ------------------------------------------------------------------


@pytest.mark.parametrize(
    "score",
    [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
)
def test_valid_engagement_scores_are_accepted(
    score,
):
    session_id = create_session()
    start_session(session_id)

    response = client.post(
        f"/api/v1/sessions/{session_id}/engagement",
        headers=auth_headers(PT001_EMAIL),
        json={"score": score},
    )

    assert response.status_code == 200, response.text
    assert response.json()["score"] == score


@pytest.mark.parametrize("score", [0, -1, 11, 100])
def test_invalid_engagement_scores_are_rejected(
    score,
):
    session_id = create_session()
    start_session(session_id)

    response = client.post(
        f"/api/v1/sessions/{session_id}/engagement",
        headers=auth_headers(PT001_EMAIL),
        json={"score": score},
    )

    assert response.status_code == 422

@pytest.mark.parametrize(
    "score",
    [1.5, 3.5, 5.5, 9.5],
)
def test_decimal_engagement_scores_are_rejected(score):
    session_id = create_session()
    start_session(session_id)

    response = client.post(
        f"/api/v1/sessions/{session_id}/engagement",
        headers=auth_headers(PT001_EMAIL),
        json={"score": score},
    )

    assert response.status_code == 422


# ------------------------------------------------------------------
# Session lifecycle
# ------------------------------------------------------------------


def test_engagement_cannot_be_recorded_for_planned_session():
    session_id = create_session()

    response = client.post(
        f"/api/v1/sessions/{session_id}/engagement",
        headers=auth_headers(PT001_EMAIL),
        json={"score": 3},
    )

    assert response.status_code == 400
    assert "in progress" in response.json()["detail"].lower()


def test_engagement_can_be_recorded_for_in_progress_session():
    session_id = create_session()
    start_session(session_id)

    response = client.post(
        f"/api/v1/sessions/{session_id}/engagement",
        headers=auth_headers(PT001_EMAIL),
        json={"score": 3},
    )

    assert response.status_code == 200

    data = response.json()

    assert data["teaching_session_id"] == session_id
    assert data["score"] == 3
    assert data["data_origin"] == "PRODUCTION"


def test_existing_engagement_can_be_updated_while_session_is_in_progress():
    session_id = create_session()
    start_session(session_id)

    first_response = client.post(
        f"/api/v1/sessions/{session_id}/engagement",
        headers=auth_headers(PT001_EMAIL),
        json={"score": 3},
    )

    assert first_response.status_code == 200

    first_data = first_response.json()
    first_id = first_data["id"]

    second_response = client.post(
        f"/api/v1/sessions/{session_id}/engagement",
        headers=auth_headers(PT001_EMAIL),
        json={"score": 5},
    )

    assert second_response.status_code == 200

    second_data = second_response.json()

    assert second_data["id"] == first_id
    assert second_data["teaching_session_id"] == session_id
    assert second_data["score"] == 5

    assert get_engagement_count(session_id) == 1


def test_engagement_cannot_be_updated_after_session_completion():
    session_id = create_session()
    start_session(session_id)

    create_response = client.post(
        f"/api/v1/sessions/{session_id}/engagement",
        headers=auth_headers(PT001_EMAIL),
        json={"score": 3},
    )

    assert create_response.status_code == 200

    prepare_session_for_completion_without_engagement(
        session_id,
        PT001_EMAIL,
    )

    complete_session(session_id)

    response = client.post(
        f"/api/v1/sessions/{session_id}/engagement",
        headers=auth_headers(PT001_EMAIL),
        json={"score": 5},
    )

    assert response.status_code == 400
    assert "in progress" in response.json()["detail"].lower()


def test_engagement_cannot_be_created_after_session_completion():
    session_id = create_session()
    start_session(session_id)

    engagement_response = client.post(
            f"/api/v1/sessions/{session_id}/engagement",
            headers=auth_headers(PT001_EMAIL),
            json={"score": 8},
    )

    assert engagement_response.status_code == 200

    prepare_session_for_completion_without_engagement(
        session_id,
        PT001_EMAIL,
    )

    complete_session(session_id)

    response = client.post(
        f"/api/v1/sessions/{session_id}/engagement",
        headers=auth_headers(PT001_EMAIL),
        json={"score": 4},
    )

    assert response.status_code == 400


# ------------------------------------------------------------------
# GET engagement
# ------------------------------------------------------------------


def test_get_engagement_before_submission_returns_null():
    session_id = create_session()

    response = client.get(
        f"/api/v1/sessions/{session_id}/engagement",
        headers=auth_headers(PT001_EMAIL),
    )

    assert response.status_code == 200
    assert response.json() is None


def test_get_submitted_engagement():
    session_id = create_session()
    start_session(session_id)

    create_response = client.post(
        f"/api/v1/sessions/{session_id}/engagement",
        headers=auth_headers(PT001_EMAIL),
        json={"score": 4},
    )

    assert create_response.status_code == 200

    response = client.get(
        f"/api/v1/sessions/{session_id}/engagement",
        headers=auth_headers(PT001_EMAIL),
    )

    assert response.status_code == 200

    data = response.json()

    assert data["teaching_session_id"] == session_id
    assert data["score"] == 4
    assert data["data_origin"] == "PRODUCTION"


# ------------------------------------------------------------------
# Authorization / school scope
# ------------------------------------------------------------------


def test_para_teacher_can_access_engagement_for_own_school():
    session_id = create_session(PT001_EMAIL)

    response = client.get(
        f"/api/v1/sessions/{session_id}/engagement",
        headers=auth_headers(PT001_EMAIL),
    )

    assert response.status_code == 200


def test_para_teacher_cannot_access_engagement_for_another_school():
    session_id = create_session(PT001_EMAIL)

    response = client.get(
        f"/api/v1/sessions/{session_id}/engagement",
        headers=auth_headers(PT002_EMAIL),
    )

    assert response.status_code == 403


def test_para_teacher_cannot_record_engagement_for_another_school():
    session_id = create_session(PT001_EMAIL)

    response = client.post(
        f"/api/v1/sessions/{session_id}/engagement",
        headers=auth_headers(PT002_EMAIL),
        json={"score": 3},
    )

    assert response.status_code == 403


def test_management_can_view_engagement_project_wide():
    """
    Management has engagement.view but no demo account is currently seeded.
    """
    pytest.skip(
        "Management demo user is not currently seeded."
    )


def test_management_cannot_create_engagement():
    """
    Management does not have engagement.create, but no demo account
    is currently seeded.
    """
    pytest.skip(
        "Management demo user is not currently seeded."
    )


def test_stem_coordinator_can_view_engagement_project_wide():
    """
    STEM Coordinator has engagement.view but no demo account is
    currently seeded.
    """
    pytest.skip(
        "STEM Coordinator demo user is not currently seeded."
    )


def test_stem_coordinator_cannot_create_engagement():
    """
    STEM Coordinator does not have engagement.create, but no demo
    account is currently seeded.
    """
    pytest.skip(
        "STEM Coordinator demo user is not currently seeded."
    )


def test_data_manager_can_view_engagement_project_wide():
    session_id = create_session(PT001_EMAIL)

    response = client.get(
        f"/api/v1/sessions/{session_id}/engagement",
        headers=auth_headers(DATA_MANAGER_EMAIL),
    )

    assert response.status_code == 200


def test_data_manager_can_create_engagement():
    session_id = create_session(PT001_EMAIL)
    start_session(session_id)

    response = client.post(
        f"/api/v1/sessions/{session_id}/engagement",
        headers=auth_headers(DATA_MANAGER_EMAIL),
        json={"score": 4},
    )

    assert response.status_code == 200


def test_platform_owner_can_view_engagement():
    """
    Platform Owner is created separately with an interactive password.
    A dedicated test fixture is required before this authorization case
    can be exercised automatically.
    """
    pytest.skip(
        "Platform Owner uses a separately created credential; "
        "dedicated test fixture not yet configured."
    )


def test_platform_owner_can_create_engagement():
    """
    Platform Owner is created separately with an interactive password.
    A dedicated test fixture is required before this authorization case
    can be exercised automatically.
    """
    pytest.skip(
        "Platform Owner uses a separately created credential; "
        "dedicated test fixture not yet configured."
    )


# ------------------------------------------------------------------
# Data integrity
# ------------------------------------------------------------------


def test_nonexistent_session_returns_404():
    fake_session_id = str(uuid.uuid4())

    response = client.get(
        f"/api/v1/sessions/{fake_session_id}/engagement",
        headers=auth_headers(PT001_EMAIL),
    )

    assert response.status_code == 404


def test_nonexistent_session_cannot_create_engagement():
    fake_session_id = str(uuid.uuid4())

    response = client.post(
        f"/api/v1/sessions/{fake_session_id}/engagement",
        headers=auth_headers(PT001_EMAIL),
        json={"score": 3},
    )

    assert response.status_code == 404


def test_update_does_not_create_second_engagement_record():
    session_id = create_session()
    start_session(session_id)

    first_response = client.post(
        f"/api/v1/sessions/{session_id}/engagement",
        headers=auth_headers(PT001_EMAIL),
        json={"score": 3},
    )

    assert first_response.status_code == 200

    first_id = first_response.json()["id"]

    assert get_engagement_count(session_id) == 1

    second_response = client.post(
        f"/api/v1/sessions/{session_id}/engagement",
        headers=auth_headers(PT001_EMAIL),
        json={"score": 5},
    )

    assert second_response.status_code == 200

    second_id = second_response.json()["id"]

    assert second_id == first_id
    assert get_engagement_count(session_id) == 1

    engagement = get_engagement_from_db(session_id)

    assert engagement is not None
    assert str(engagement.id) == first_id
    assert engagement.score == 5


def test_engagement_data_origin_is_server_controlled():
    session_id = create_session()
    start_session(session_id)

    response = client.post(
        f"/api/v1/sessions/{session_id}/engagement",
        headers=auth_headers(PT001_EMAIL),
        json={
            "score": 4,
            "data_origin": "DEMO",
        },
    )

    # data_origin is not part of the input model, so the
    # client-supplied value must not alter the stored value.
    assert response.status_code == 200
    assert response.json()["data_origin"] == "PRODUCTION"

    engagement = get_engagement_from_db(session_id)

    assert engagement is not None
    assert engagement.data_origin == "PRODUCTION"
