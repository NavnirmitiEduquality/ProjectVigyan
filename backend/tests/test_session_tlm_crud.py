import io
import os
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient
from sqlalchemy import func

from app.database import SessionLocal
from app.main import app
from app.models import (
    ClassDivision,
    SessionTLM,
    Student,
    TeachingSession,
    TLM,
)

load_dotenv()

DEMO_PASSWORD = os.getenv("DEMO_USER_PASSWORD")

if not DEMO_PASSWORD:
    raise RuntimeError(
        "DEMO_USER_PASSWORD must be configured in .env "
        "before running Session TLM CRUD tests."
    )

client = TestClient(app)

PT001_EMAIL = "pt001@demo.vigyan.com"
PT002_EMAIL = "pt002@demo.vigyan.com"
MANAGEMENT_EMAIL = "management@demo.vigyan.com"
STEM_EMAIL = "stem@demo.vigyan.com"
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

def optional_auth_headers(email: str) -> dict[str, str] | None:
    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": email,
            "password": DEMO_PASSWORD,
        },
    )

    if response.status_code == 401:
        return None

    assert response.status_code == 200, response.text

    token = response.json()["access_token"]

    return {
        "Authorization": f"Bearer {token}",
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


def get_first_class_division(
    email: str = PT001_EMAIL,
):
    db = SessionLocal()

    try:
        school_id = get_para_teacher_school_id(email)

        class_division = (
            db.query(ClassDivision)
            .filter(
                ClassDivision.school_id == school_id,
            )
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


def complete_session(
    session_id: str,
    email: str = PT001_EMAIL,
) -> None:
    response = client.post(
        f"/api/v1/sessions/{session_id}/complete",
        headers=auth_headers(email),
    )

    assert response.status_code == 200, response.text


def get_tlm_by_name(name: str) -> TLM:
    db = SessionLocal()

    try:
        tlm = (
            db.query(TLM)
            .filter(TLM.name == name)
            .first()
        )

        assert tlm is not None, (
            f"TLM '{name}' must exist in the seeded master."
        )

        return tlm

    finally:
        db.close()


def get_active_tlm(
    exclude_names: tuple[str, ...] = (),
) -> TLM:
    db = SessionLocal()

    try:
        query = (
            db.query(TLM)
            .filter(TLM.is_active.is_(True))
        )

        if exclude_names:
            query = query.filter(
                ~TLM.name.in_(exclude_names)
            )

        tlm = query.order_by(TLM.name).first()

        assert tlm is not None

        return tlm

    finally:
        db.close()


def get_session_tlm_count(
    session_id: str,
) -> int:
    db = SessionLocal()

    try:
        return (
            db.query(func.count(SessionTLM.id))
            .filter(
                SessionTLM.teaching_session_id
                == uuid.UUID(session_id),
            )
            .scalar()
        )

    finally:
        db.close()


def create_session_tlm(
    session_id: str,
    email: str = PT001_EMAIL,
    *,
    tlm_id: str | None = None,
    quantity: int = 1,
    usage: str = "Used for the activity.",
):
    if tlm_id is None:
        tlm_id = str(
            get_active_tlm().id
        )

    return client.post(
        f"/api/v1/sessions/{session_id}/tlms",
        headers=auth_headers(email),
        data={
            "tlm_id": tlm_id,
            "quantity": str(quantity),
            "usage": usage,
        },
    )


def jpeg_bytes() -> bytes:
    """
    Small valid JPEG generated from a known byte sequence.
    """
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


def prepare_session_for_completion_without_tlm(
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
        headers=headers,
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
        headers=headers,
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


def test_get_session_tlms_requires_authentication():
    session_id = str(uuid.uuid4())

    response = client.get(
        f"/api/v1/sessions/{session_id}/tlms",
    )

    assert response.status_code == 401


def test_get_single_session_tlm_requires_authentication():
    response = client.get(
        "/api/v1/sessions/"
        f"{uuid.uuid4()}/tlms/"
        f"{uuid.uuid4()}",
    )

    assert response.status_code == 401


def test_create_session_tlm_requires_authentication():
    session_id = str(uuid.uuid4())
    tlm = get_active_tlm()

    response = client.post(
        f"/api/v1/sessions/{session_id}/tlms",
        data={
            "tlm_id": str(tlm.id),
            "quantity": "1",
        },
    )

    assert response.status_code == 401


# ------------------------------------------------------------------
# Basic CRUD
# ------------------------------------------------------------------


def test_para_teacher_can_create_session_tlm():
    session_id = create_in_progress_session()

    tlm = get_active_tlm()

    response = create_session_tlm(
        session_id,
        tlm_id=str(tlm.id),
        quantity=2,
        usage="Students used the models during the activity.",
    )

    assert response.status_code == 201, response.text

    data = response.json()

    assert data["teaching_session_id"] == session_id
    assert data["tlm_id"] == str(tlm.id)
    assert data["tlm_name"] == tlm.name
    assert data["quantity"] == 2
    assert (
        data["usage"]
        == "Students used the models during the activity."
    )
    assert data["photo_id"] is None
    assert data["data_origin"] == "PRODUCTION"

    assert get_session_tlm_count(session_id) == 1


def test_para_teacher_can_list_session_tlms():
    session_id = create_in_progress_session()

    tlm = get_active_tlm()

    create_response = create_session_tlm(
        session_id,
        tlm_id=str(tlm.id),
    )

    assert create_response.status_code == 201

    response = client.get(
        f"/api/v1/sessions/{session_id}/tlms",
        headers=auth_headers(PT001_EMAIL),
    )

    assert response.status_code == 200, response.text

    data = response.json()

    assert data["total"] == 1
    assert len(data["items"]) == 1
    assert data["items"][0]["tlm_id"] == str(tlm.id)


def test_para_teacher_can_get_single_session_tlm():
    session_id = create_in_progress_session()

    response = create_session_tlm(session_id)

    assert response.status_code == 201

    session_tlm_id = response.json()["id"]

    response = client.get(
        f"/api/v1/sessions/"
        f"{session_id}/tlms/{session_tlm_id}",
        headers=auth_headers(PT001_EMAIL),
    )

    assert response.status_code == 200

    data = response.json()

    assert data["id"] == session_tlm_id
    assert data["teaching_session_id"] == session_id


def test_para_teacher_can_update_session_tlm():
    session_id = create_in_progress_session()

    first_tlm = get_active_tlm()

    create_response = create_session_tlm(
        session_id,
        tlm_id=str(first_tlm.id),
        quantity=1,
        usage="Initial usage.",
    )

    assert create_response.status_code == 201

    session_tlm_id = create_response.json()["id"]

    response = client.patch(
        f"/api/v1/sessions/"
        f"{session_id}/tlms/{session_tlm_id}",
        headers=auth_headers(PT001_EMAIL),
        data={
            "quantity": "3",
            "usage": "Updated usage.",
        },
    )

    assert response.status_code == 200, response.text

    data = response.json()

    assert data["id"] == session_tlm_id
    assert data["quantity"] == 3
    assert data["usage"] == "Updated usage."


def test_data_manager_can_delete_session_tlm():
    session_id = create_in_progress_session()

    response = create_session_tlm(session_id)

    assert response.status_code == 201

    session_tlm_id = response.json()["id"]

    response = client.delete(
        f"/api/v1/sessions/"
        f"{session_id}/tlms/{session_tlm_id}",
        headers=auth_headers(DATA_MANAGER_EMAIL),
    )

    assert response.status_code == 204
    assert response.content == b""

    assert get_session_tlm_count(session_id) == 0


# ------------------------------------------------------------------
# Role permissions
# ------------------------------------------------------------------


def test_para_teacher_cannot_delete_session_tlm():
    session_id = create_in_progress_session()

    response = create_session_tlm(session_id)

    assert response.status_code == 201

    session_tlm_id = response.json()["id"]

    response = client.delete(
        f"/api/v1/sessions/"
        f"{session_id}/tlms/{session_tlm_id}",
        headers=auth_headers(PT001_EMAIL),
    )

    assert response.status_code == 403


def test_management_can_view_session_tlms():
    session_id = create_in_progress_session()

    response = create_session_tlm(session_id)

    assert response.status_code == 201

    headers = optional_auth_headers(MANAGEMENT_EMAIL)

    if headers is None:
        pytest.skip("Management demo user is not seeded")

    response = client.get(
        f"/api/v1/sessions/{session_id}/tlms",
        headers=headers,
    )

    assert response.status_code == 200
    data = response.json()

    assert data["total"] == 1
    assert len(data["items"]) == 1


def test_management_cannot_create_session_tlm():
    session_id = create_in_progress_session()

    tlm = get_active_tlm()

    headers = optional_auth_headers(MANAGEMENT_EMAIL)

    if headers is None:
        pytest.skip("Management demo user is not seeded")

    response = client.post(
        f"/api/v1/sessions/{session_id}/tlms",
        headers=headers,
        data={
            "tlm_id": str(tlm.id),
            "quantity": "1",
        },
    )

    assert response.status_code == 403

def test_stem_coordinator_can_view_session_tlms():
    session_id = create_in_progress_session()

    response = create_session_tlm(session_id)

    assert response.status_code == 201

    headers = optional_auth_headers(STEM_EMAIL)

    if headers is None:
        pytest.skip("STEM Coordinator demo user is not seeded")

    response = client.get(
        f"/api/v1/sessions/{session_id}/tlms",
        headers=headers,
    )

    assert response.status_code == 200

    data = response.json()

    assert data["total"] == 1
    assert len(data["items"]) == 1


def test_stem_coordinator_cannot_create_session_tlm():
    session_id = create_in_progress_session()

    tlm = get_active_tlm()

    headers = optional_auth_headers(STEM_EMAIL)

    if headers is None:
        pytest.skip("STEM Coordinator demo user is not seeded")

    response = client.post(
        f"/api/v1/sessions/{session_id}/tlms",
        headers=headers,
        data={
            "tlm_id": str(tlm.id),
            "quantity": "1",
        },
    )

    assert response.status_code == 403


# ------------------------------------------------------------------
# School authorization
# ------------------------------------------------------------------


def test_para_teacher_cannot_view_another_school_session_tlms():
    pt002_session = create_in_progress_session(
        PT002_EMAIL,
    )

    response = client.get(
        f"/api/v1/sessions/{pt002_session}/tlms",
        headers=auth_headers(PT001_EMAIL),
    )

    assert response.status_code == 403


def test_para_teacher_cannot_create_tlm_for_another_school():
    pt002_session = create_in_progress_session(
        PT002_EMAIL,
    )

    tlm = get_active_tlm()

    response = client.post(
        f"/api/v1/sessions/{pt002_session}/tlms",
        headers=auth_headers(PT001_EMAIL),
        data={
            "tlm_id": str(tlm.id),
            "quantity": "1",
        },
    )

    assert response.status_code == 403


# ------------------------------------------------------------------
# Session lifecycle
# ------------------------------------------------------------------


def test_session_tlm_cannot_be_created_for_planned_session():
    class_division = get_first_class_division()

    response = client.post(
        "/api/v1/sessions",
        headers=auth_headers(PT001_EMAIL),
        json={
            "class_division_id": str(class_division.id),
            "session_date": str(date.today()),
        },
    )

    assert response.status_code == 201

    session_id = response.json()["id"]

    response = create_session_tlm(session_id)

    assert response.status_code == 409


def test_session_tlm_cannot_be_modified_after_completion():
    session_id = create_in_progress_session()

    response = create_session_tlm(session_id)

    assert response.status_code == 201

    session_tlm_id = response.json()["id"]

    prepare_session_for_completion_without_tlm(session_id)

    complete_session(session_id)

    response = client.patch(
        f"/api/v1/sessions/"
        f"{session_id}/tlms/{session_tlm_id}",
        headers=auth_headers(PT001_EMAIL),
        data={
            "quantity": "2",
        },
    )

    assert response.status_code == 409


def test_session_tlm_cannot_be_deleted_after_completion():
    session_id = create_in_progress_session()

    response = create_session_tlm(session_id)

    assert response.status_code == 201

    session_tlm_id = response.json()["id"]

    prepare_session_for_completion_without_tlm(session_id)

    complete_session(session_id)

    response = client.delete(
        f"/api/v1/sessions/"
        f"{session_id}/tlms/{session_tlm_id}",
        headers=auth_headers(DATA_MANAGER_EMAIL),
    )

    assert response.status_code == 409


# ------------------------------------------------------------------
# Quantity validation
# ------------------------------------------------------------------


@pytest.mark.parametrize(
    "quantity",
    [0, -1, -5],
)
def test_normal_tlm_rejects_non_positive_quantity(
    quantity,
):
    session_id = create_in_progress_session()

    tlm = get_active_tlm(
        exclude_names=("NA - No TLM Used",),
    )

    response = create_session_tlm(
        session_id,
        tlm_id=str(tlm.id),
        quantity=quantity,
    )

    assert response.status_code == 400


def test_na_tlm_requires_zero_quantity():
    session_id = create_in_progress_session()

    na_tlm = get_tlm_by_name(
        "NA - No TLM Used",
    )

    response = create_session_tlm(
        session_id,
        tlm_id=str(na_tlm.id),
        quantity=0,
        usage="No TLM was used.",
    )

    assert response.status_code == 201, response.text

    data = response.json()

    assert data["tlm_name"] == "NA - No TLM Used"
    assert data["quantity"] == 0


def test_na_tlm_rejects_nonzero_quantity():
    session_id = create_in_progress_session()

    na_tlm = get_tlm_by_name(
        "NA - No TLM Used",
    )

    response = create_session_tlm(
        session_id,
        tlm_id=str(na_tlm.id),
        quantity=1,
    )

    assert response.status_code == 400


# ------------------------------------------------------------------
# Duplicate / NA conflicts
# ------------------------------------------------------------------


def test_same_tlm_cannot_be_added_twice():
    session_id = create_in_progress_session()

    tlm = get_active_tlm()

    first_response = create_session_tlm(
        session_id,
        tlm_id=str(tlm.id),
    )

    assert first_response.status_code == 201

    second_response = create_session_tlm(
        session_id,
        tlm_id=str(tlm.id),
    )

    assert second_response.status_code == 409


def test_na_tlm_is_mutually_exclusive():
    session_id = create_in_progress_session()

    na_tlm = get_tlm_by_name(
        "NA - No TLM Used",
    )

    normal_tlm = get_active_tlm(
        exclude_names=("NA - No TLM Used",),
    )

    first_response = create_session_tlm(
        session_id,
        tlm_id=str(na_tlm.id),
        quantity=0,
    )

    assert first_response.status_code == 201

    second_response = create_session_tlm(
        session_id,
        tlm_id=str(normal_tlm.id),
        quantity=1,
    )

    assert second_response.status_code == 409


def test_normal_tlm_cannot_be_added_when_na_exists():
    session_id = create_in_progress_session()

    na_tlm = get_tlm_by_name(
        "NA - No TLM Used",
    )

    normal_tlm = get_active_tlm(
        exclude_names=("NA - No TLM Used",),
    )

    first_response = create_session_tlm(
        session_id,
        tlm_id=str(normal_tlm.id),
    )

    assert first_response.status_code == 201

    response = create_session_tlm(
        session_id,
        tlm_id=str(na_tlm.id),
        quantity=0,
    )

    assert response.status_code == 409


# ------------------------------------------------------------------
# TLM master validation
# ------------------------------------------------------------------


def test_nonexistent_tlm_returns_404():
    session_id = create_in_progress_session()

    response = create_session_tlm(
        session_id,
        tlm_id=str(uuid.uuid4()),
    )

    assert response.status_code == 404


def test_inactive_tlm_cannot_be_added():
    session_id = create_in_progress_session()

    db = SessionLocal()

    try:
        tlm = get_active_tlm()

        tlm_record = (
            db.query(TLM)
            .filter(TLM.id == tlm.id)
            .first()
        )

        assert tlm_record is not None

        tlm_record.is_active = False
        db.commit()

        response = create_session_tlm(
            session_id,
            tlm_id=str(tlm.id),
        )

        assert response.status_code == 409

    finally:
        tlm_record.is_active = True
        db.commit()
        db.close()


# ------------------------------------------------------------------
# Nested resource integrity
# ------------------------------------------------------------------


def test_session_tlm_from_another_session_returns_404():
    session_one = create_in_progress_session()
    session_two = create_in_progress_session()

    response = create_session_tlm(session_one)

    assert response.status_code == 201

    session_tlm_id = response.json()["id"]

    response = client.get(
        f"/api/v1/sessions/"
        f"{session_two}/tlms/{session_tlm_id}",
        headers=auth_headers(PT001_EMAIL),
    )

    assert response.status_code == 404


# ------------------------------------------------------------------
# Photo validation
# ------------------------------------------------------------------


def test_tlm_photo_can_be_uploaded():
    session_id = create_in_progress_session()

    tlm = get_active_tlm()

    response = client.post(
        f"/api/v1/sessions/{session_id}/tlms",
        headers=auth_headers(PT001_EMAIL),
        data={
            "tlm_id": str(tlm.id),
            "quantity": "1",
            **photo_form_data(),
        },
        files={
            "photo": (
                "activity.jpg",
                jpeg_bytes(),
                "image/jpeg",
            ),
        },
    )

    assert response.status_code == 201, response.text

    data = response.json()

    assert data["photo_id"] is not None


def test_non_jpeg_photo_is_rejected():
    session_id = create_in_progress_session()

    tlm = get_active_tlm()

    response = client.post(
        f"/api/v1/sessions/{session_id}/tlms",
        headers=auth_headers(PT001_EMAIL),
        data={
            "tlm_id": str(tlm.id),
            "quantity": "1",
            **photo_form_data(),
        },
        files={
            "photo": (
                "activity.png",
                b"not-a-jpeg",
                "image/png",
            ),
        },
    )

    assert response.status_code == 400


def test_photo_requires_metadata():
    session_id = create_in_progress_session()

    tlm = get_active_tlm()

    response = client.post(
        f"/api/v1/sessions/{session_id}/tlms",
        headers=auth_headers(PT001_EMAIL),
        data={
            "tlm_id": str(tlm.id),
            "quantity": "1",
        },
        files={
            "photo": (
                "activity.jpg",
                jpeg_bytes(),
                "image/jpeg",
            ),
        },
    )

    assert response.status_code == 400


def test_photo_metadata_without_photo_is_rejected():
    session_id = create_in_progress_session()

    tlm = get_active_tlm()

    response = client.post(
        f"/api/v1/sessions/{session_id}/tlms",
        headers=auth_headers(PT001_EMAIL),
        data={
            "tlm_id": str(tlm.id),
            "quantity": "1",
            "captured_at": datetime.now(
                timezone.utc
            ).isoformat(),
            "latitude": "19.076000",
            "longitude": "72.877700",
        },
    )

    assert response.status_code == 400


def test_photo_and_remove_photo_cannot_be_combined():
    session_id = create_in_progress_session()

    response = create_session_tlm(session_id)

    assert response.status_code == 201

    session_tlm_id = response.json()["id"]

    response = client.patch(
        f"/api/v1/sessions/"
        f"{session_id}/tlms/{session_tlm_id}",
        headers=auth_headers(PT001_EMAIL),
        data={
            "remove_photo": "true",
            **photo_form_data(),
        },
        files={
            "photo": (
                "replacement.jpg",
                jpeg_bytes(),
                "image/jpeg",
            ),
        },
    )

    assert response.status_code == 400


# ------------------------------------------------------------------
# Photo update lifecycle
# ------------------------------------------------------------------


def test_session_tlm_photo_can_be_replaced():
    session_id = create_in_progress_session()

    tlm = get_active_tlm()

    create_response = client.post(
        f"/api/v1/sessions/{session_id}/tlms",
        headers=auth_headers(PT001_EMAIL),
        data={
            "tlm_id": str(tlm.id),
            "quantity": "1",
            **photo_form_data(),
        },
        files={
            "photo": (
                "first.jpg",
                jpeg_bytes(),
                "image/jpeg",
            ),
        },
    )

    assert create_response.status_code == 201, (
        create_response.text
    )

    first_photo_id = create_response.json()["photo_id"]

    update_response = client.patch(
        f"/api/v1/sessions/"
        f"{session_id}/tlms/"
        f"{create_response.json()['id']}",
        headers=auth_headers(PT001_EMAIL),
        data=photo_form_data(),
        files={
            "photo": (
                "second.jpg",
                jpeg_bytes(),
                "image/jpeg",
            ),
        },
    )

    assert update_response.status_code == 200, (
        update_response.text
    )

    data = update_response.json()

    assert data["photo_id"] is not None
    assert data["photo_id"] != first_photo_id


def test_session_tlm_photo_can_be_removed():
    session_id = create_in_progress_session()

    tlm = get_active_tlm()

    create_response = client.post(
        f"/api/v1/sessions/{session_id}/tlms",
        headers=auth_headers(PT001_EMAIL),
        data={
            "tlm_id": str(tlm.id),
            "quantity": "1",
            **photo_form_data(),
        },
        files={
            "photo": (
                "activity.jpg",
                jpeg_bytes(),
                "image/jpeg",
            ),
        },
    )

    assert create_response.status_code == 201

    session_tlm_id = create_response.json()["id"]

    response = client.patch(
        f"/api/v1/sessions/"
        f"{session_id}/tlms/{session_tlm_id}",
        headers=auth_headers(PT001_EMAIL),
        data={
            "remove_photo": "true",
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["photo_id"] is None


def test_session_tlm_photo_is_deleted_when_record_is_deleted():
    session_id = create_in_progress_session()

    tlm = get_active_tlm()

    create_response = client.post(
        f"/api/v1/sessions/{session_id}/tlms",
        headers=auth_headers(PT001_EMAIL),
        data={
            "tlm_id": str(tlm.id),
            "quantity": "1",
            **photo_form_data(),
        },
        files={
            "photo": (
                "activity.jpg",
                jpeg_bytes(),
                "image/jpeg",
            ),
        },
    )

    assert create_response.status_code == 201

    session_tlm_id = create_response.json()["id"]

    response = client.delete(
        f"/api/v1/sessions/"
        f"{session_id}/tlms/{session_tlm_id}",
        headers=auth_headers(DATA_MANAGER_EMAIL),
    )

    assert response.status_code == 204

    db = SessionLocal()

    try:
        assert (
            db.query(SessionTLM)
            .filter(
                SessionTLM.id
                == uuid.UUID(session_tlm_id),
            )
            .first()
            is None
        )

    finally:
        db.close()


# ------------------------------------------------------------------
# Server-controlled fields
# ------------------------------------------------------------------


def test_client_cannot_control_data_origin():
    session_id = create_in_progress_session()

    tlm = get_active_tlm()

    response = client.post(
        f"/api/v1/sessions/{session_id}/tlms",
        headers=auth_headers(PT001_EMAIL),
        data={
            "tlm_id": str(tlm.id),
            "quantity": "1",
            "data_origin": "DEMO",
        },
    )

    assert response.status_code == 201, response.text
    assert response.json()["data_origin"] == "PRODUCTION"


# ------------------------------------------------------------------
# Missing resources
# ------------------------------------------------------------------


def test_nonexistent_session_returns_404():
    tlm = get_active_tlm()

    response = client.post(
        f"/api/v1/sessions/{uuid.uuid4()}/tlms",
        headers=auth_headers(PT001_EMAIL),
        data={
            "tlm_id": str(tlm.id),
            "quantity": "1",
        },
    )

    assert response.status_code == 404


def test_nonexistent_session_tlm_returns_404():
    session_id = create_in_progress_session()

    response = client.get(
        f"/api/v1/sessions/"
        f"{session_id}/tlms/{uuid.uuid4()}",
        headers=auth_headers(PT001_EMAIL),
    )

    assert response.status_code == 404
