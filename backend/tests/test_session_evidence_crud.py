import io
import os
import uuid
from datetime import date, datetime, timezone

import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient
from sqlalchemy import func

from app.database import SessionLocal
from app.main import app
from app.models import (
    Photo,
    SessionEvidence,
    Student,
    TeachingSession,
    TLM,
)

load_dotenv()

DEMO_PASSWORD = os.getenv("DEMO_USER_PASSWORD")

if not DEMO_PASSWORD:
    raise RuntimeError(
        "DEMO_USER_PASSWORD must be configured in .env "
        "before running Session Evidence CRUD tests."
    )

client = TestClient(app)

PT001_EMAIL = "pt001@demo.vigyan.com"
PT002_EMAIL = "pt002@demo.vigyan.com"
DATA_MANAGER_EMAIL = "dm001@demo.vigyan.com"


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


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


def auth_headers(email: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {login(email)}",
    }


def get_para_teacher_school_id(email: str):
    from app.models import User, UserAssignment

    db = SessionLocal()

    try:
        user = (
            db.query(User)
            .filter(User.email == email)
            .first()
        )

        assert user is not None

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


def get_first_class_division(email: str = PT001_EMAIL):
    from app.models import ClassDivision

    db = SessionLocal()

    try:
        school_id = get_para_teacher_school_id(email)

        class_division = (
            db.query(ClassDivision)
            .filter(ClassDivision.school_id == school_id)
            .order_by(ClassDivision.created_at)
            .first()
        )

        assert class_division is not None

        return class_division

    finally:
        db.close()


def create_in_progress_session(
    email: str = PT001_EMAIL,
) -> str:
    class_division = get_first_class_division(email)

    headers = auth_headers(email)

    create_response = client.post(
        "/api/v1/sessions",
        headers=headers,
        json={
            "class_division_id": str(class_division.id),
            "session_date": str(date.today()),
        },
    )

    assert create_response.status_code == 201, (
        create_response.text
    )

    session_id = create_response.json()["id"]

    start_response = client.post(
        f"/api/v1/sessions/{session_id}/start",
        headers=headers,
    )

    assert start_response.status_code == 200, (
        start_response.text
    )

    assert start_response.json()["status"] == "IN_PROGRESS"

    return session_id


def jpeg_bytes() -> bytes:
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

    return buffer.getvalue()


def photo_form_data():
    return {
        "captured_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "latitude": "19.076000",
        "longitude": "72.877700",
    }


def evidence_photo():
    return {
        "photo": (
            "session-evidence.jpg",
            jpeg_bytes(),
            "image/jpeg",
        )
    }


def create_session_evidence(
    session_id: str,
    email: str = PT001_EMAIL,
):
    return client.post(
        f"/api/v1/sessions/{session_id}/evidence",
        headers=auth_headers(email),
        files=evidence_photo(),
        data=photo_form_data(),
    )


def get_evidence_count(session_id: str) -> int:
    db = SessionLocal()

    try:
        return (
            db.query(func.count(SessionEvidence.id))
            .filter(
                SessionEvidence.teaching_session_id
                == uuid.UUID(session_id),
            )
            .scalar()
        )

    finally:
        db.close()


def get_evidence(session_id: str):
    db = SessionLocal()

    try:
        return (
            db.query(SessionEvidence)
            .filter(
                SessionEvidence.teaching_session_id
                == uuid.UUID(session_id),
            )
            .first()
        )

    finally:
        db.close()


def get_photo(photo_id):
    db = SessionLocal()

    try:
        return (
            db.query(Photo)
            .filter(Photo.id == photo_id)
            .first()
        )

    finally:
        db.close()


# ------------------------------------------------------------------
# Authentication
# ------------------------------------------------------------------


def test_get_session_evidence_requires_authentication():
    response = client.get(
        f"/api/v1/sessions/{uuid.uuid4()}/evidence",
    )

    assert response.status_code == 401


def test_get_single_session_evidence_requires_authentication():
    response = client.get(
        f"/api/v1/sessions/{uuid.uuid4()}/evidence/"
        f"{uuid.uuid4()}",
    )

    assert response.status_code == 401


def test_create_session_evidence_requires_authentication():
    response = client.post(
        f"/api/v1/sessions/{uuid.uuid4()}/evidence",
        files=evidence_photo(),
        data=photo_form_data(),
    )

    assert response.status_code == 401


def test_update_session_evidence_requires_authentication():
    response = client.patch(
        f"/api/v1/sessions/{uuid.uuid4()}/evidence",
        files=evidence_photo(),
        data=photo_form_data(),
    )

    assert response.status_code == 401


def test_delete_session_evidence_requires_authentication():
    response = client.delete(
        f"/api/v1/sessions/{uuid.uuid4()}/evidence",
    )

    assert response.status_code == 401


# ------------------------------------------------------------------
# Permissions
# ------------------------------------------------------------------


def test_data_manager_without_evidence_create_permission_is_rejected():
    session_id = create_in_progress_session()

    response = client.post(
        f"/api/v1/sessions/{session_id}/evidence",
        headers=auth_headers(DATA_MANAGER_EMAIL),
        files=evidence_photo(),
        data=photo_form_data(),
    )

    assert response.status_code == 403


# ------------------------------------------------------------------
# CREATE
# ------------------------------------------------------------------


def test_create_valid_session_evidence():
    session_id = create_in_progress_session()

    response = create_session_evidence(session_id)

    assert response.status_code == 201, response.text

    body = response.json()

    assert body["teaching_session_id"] == session_id
    assert body["photo_id"]
    assert body["data_origin"] == "PRODUCTION"
    assert body["id"]

    assert get_evidence_count(session_id) == 1

    evidence = get_evidence(session_id)

    assert evidence is not None
    assert evidence.photo_id == uuid.UUID(body["photo_id"])

    photo = get_photo(evidence.photo_id)

    assert photo is not None
    assert photo.photo_category == "SESSION_EVIDENCE"
    assert photo.content_type == "image/jpeg"


def test_create_duplicate_session_evidence_is_rejected():
    session_id = create_in_progress_session()

    first = create_session_evidence(session_id)
    assert first.status_code == 201, first.text

    second = create_session_evidence(session_id)

    assert second.status_code == 409
    assert second.json()["detail"] == (
        "Session evidence already exists for this teaching session."
    )

    assert get_evidence_count(session_id) == 1


def test_create_missing_photo_is_rejected():
    session_id = create_in_progress_session()

    response = client.post(
        f"/api/v1/sessions/{session_id}/evidence",
        headers=auth_headers(PT001_EMAIL),
        data=photo_form_data(),
    )

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "A session evidence photo is required."
    )


def test_create_non_jpeg_is_rejected():
    session_id = create_in_progress_session()

    response = client.post(
        f"/api/v1/sessions/{session_id}/evidence",
        headers=auth_headers(PT001_EMAIL),
        files={
            "photo": (
                "evidence.txt",
                b"not-a-jpeg",
                "text/plain",
            )
        },
        data=photo_form_data(),
    )

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "Only JPEG photos are supported."
    )


@pytest.mark.parametrize(
    "missing_field",
    [
        "captured_at",
        "latitude",
        "longitude",
    ],
)
def test_create_requires_photo_metadata(missing_field):
    session_id = create_in_progress_session()

    data = photo_form_data()
    data.pop(missing_field)

    response = client.post(
        f"/api/v1/sessions/{session_id}/evidence",
        headers=auth_headers(PT001_EMAIL),
        files=evidence_photo(),
        data=data,
    )

    assert response.status_code == 400


# ------------------------------------------------------------------
# GET
# ------------------------------------------------------------------


def test_get_session_evidence():
    session_id = create_in_progress_session()

    create_response = create_session_evidence(session_id)
    assert create_response.status_code == 201

    evidence_id = create_response.json()["id"]

    response = client.get(
        f"/api/v1/sessions/{session_id}/evidence",
        headers=auth_headers(PT001_EMAIL),
    )

    assert response.status_code == 200

    body = response.json()

    assert body["id"] == evidence_id
    assert body["teaching_session_id"] == session_id


def test_get_single_session_evidence():
    session_id = create_in_progress_session()

    create_response = create_session_evidence(session_id)
    assert create_response.status_code == 201

    evidence_id = create_response.json()["id"]

    response = client.get(
        f"/api/v1/sessions/{session_id}/evidence/{evidence_id}",
        headers=auth_headers(PT001_EMAIL),
    )

    assert response.status_code == 200

    body = response.json()

    assert body["id"] == evidence_id
    assert body["teaching_session_id"] == session_id


def test_get_missing_session_evidence_returns_404():
    session_id = create_in_progress_session()

    response = client.get(
        f"/api/v1/sessions/{session_id}/evidence",
        headers=auth_headers(PT001_EMAIL),
    )

    assert response.status_code == 404
    assert response.json()["detail"] == (
        "Session evidence does not exist."
    )


# ------------------------------------------------------------------
# REPLACE / RETAKE
# ------------------------------------------------------------------


def test_replace_session_evidence():
    session_id = create_in_progress_session()

    first = create_session_evidence(session_id)
    assert first.status_code == 201

    first_body = first.json()
    first_photo_id = first_body["photo_id"]

    second = client.patch(
        f"/api/v1/sessions/{session_id}/evidence",
        headers=auth_headers(PT001_EMAIL),
        files=evidence_photo(),
        data=photo_form_data(),
    )

    assert second.status_code == 200, second.text

    second_body = second.json()

    assert second_body["id"] == first_body["id"]
    assert second_body["teaching_session_id"] == session_id
    assert second_body["photo_id"] != first_photo_id

    assert get_evidence_count(session_id) == 1

    evidence = get_evidence(session_id)

    assert evidence is not None
    assert evidence.photo_id == uuid.UUID(
        second_body["photo_id"]
    )

    new_photo = get_photo(
        uuid.UUID(second_body["photo_id"])
    )

    assert new_photo is not None
    assert new_photo.photo_category == "SESSION_EVIDENCE"


def test_replace_missing_session_evidence_returns_404():
    session_id = create_in_progress_session()

    response = client.patch(
        f"/api/v1/sessions/{session_id}/evidence",
        headers=auth_headers(PT001_EMAIL),
        files=evidence_photo(),
        data=photo_form_data(),
    )

    assert response.status_code == 404
    assert response.json()["detail"] == (
        "Session evidence does not exist."
    )


# ------------------------------------------------------------------
# DELETE
# ------------------------------------------------------------------


def test_para_teacher_cannot_delete_session_evidence():
    session_id = create_in_progress_session()

    create_response = create_session_evidence(session_id)
    assert create_response.status_code == 201

    response = client.delete(
        f"/api/v1/sessions/{session_id}/evidence",
        headers=auth_headers(PT001_EMAIL),
    )

    assert response.status_code == 403
    assert get_evidence_count(session_id) == 1


# ------------------------------------------------------------------
# COMPLETED SESSION LOCK
# ------------------------------------------------------------------


def prepare_session_for_completion_without_evidence(
    session_id: str,
) -> None:
    db = SessionLocal()

    try:
        session = (
            db.query(TeachingSession)
            .filter(TeachingSession.id == session_id)
            .first()
        )

        assert session is not None

        students = (
            db.query(Student)
            .filter(
                Student.class_division_id == session.class_division_id,
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

    headers = auth_headers(PT001_EMAIL)

    attendance_response = client.post(
        f"/api/v1/sessions/{session_id}/attendance",
        headers=headers,
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

    engagement_response = client.post(
        f"/api/v1/sessions/{session_id}/engagement",
        headers=headers,
        json={"score": 8},
    )

    assert engagement_response.status_code == 200, (
        engagement_response.text
    )

    tlm_response = client.post(
        f"/api/v1/sessions/{session_id}/tlms",
        headers=headers,
        data={
            "tlm_id": tlm_id,
            "quantity": "1",
            "usage": "Used for the activity.",
        },
    )

    assert tlm_response.status_code == 201, (
        tlm_response.text
    )

    feedback_response = client.patch(
        f"/api/v1/sessions/{session_id}/feedback",
        headers=headers,
        json={
            "remarks": "Session completed successfully.",
        },
    )

    assert feedback_response.status_code == 200, (
        feedback_response.text
    )


def test_session_evidence_cannot_be_created_after_session_completion():
    session_id = create_in_progress_session()

    response = create_session_evidence(session_id)
    assert response.status_code == 201

    prepare_session_for_completion_without_evidence(session_id)

    complete_response = client.post(
        f"/api/v1/sessions/{session_id}/complete",
        headers=auth_headers(PT001_EMAIL),
    )

    assert complete_response.status_code == 200, (
        complete_response.text
    )

    response = client.post(
        f"/api/v1/sessions/{session_id}/evidence",
        headers=auth_headers(PT001_EMAIL),
        files=evidence_photo(),
        data=photo_form_data(),
    )

    assert response.status_code == 409


def test_session_evidence_cannot_be_replaced_after_completion():
    session_id = create_in_progress_session()

    response = create_session_evidence(session_id)
    assert response.status_code == 201

    prepare_session_for_completion_without_evidence(session_id)

    complete_response = client.post(
        f"/api/v1/sessions/{session_id}/complete",
        headers=auth_headers(PT001_EMAIL),
    )

    assert complete_response.status_code == 200, (
        complete_response.text
    )

    response = client.patch(
        f"/api/v1/sessions/{session_id}/evidence",
        headers=auth_headers(PT001_EMAIL),
        files=evidence_photo(),
        data=photo_form_data(),
    )

    assert response.status_code == 409

# ------------------------------------------------------------------
# SCHOOL ACCESS
# ------------------------------------------------------------------


def test_para_teacher_cannot_access_another_school_session():
    session_id = create_in_progress_session(PT001_EMAIL)

    response = client.get(
        f"/api/v1/sessions/{session_id}/evidence",
        headers=auth_headers(PT002_EMAIL),
    )

    assert response.status_code == 403
