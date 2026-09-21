import os
from uuid import UUID

import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models import ClassDivision, Student

load_dotenv()

DEMO_PASSWORD = os.getenv("DEMO_USER_PASSWORD")

client = TestClient(app)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def login(email: str) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": email,
            "password": DEMO_PASSWORD,
        },
    )

    assert response.status_code == 200, response.text

    data = response.json()
    return data["session_token"]


def auth_headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
    }


def get_demo_class_division(
    school_code: str,
    class_level: int,
    division: str,
):
    db = SessionLocal()

    try:
        class_division = (
            db.query(ClassDivision)
            .join(ClassDivision.school)
            .filter(
                ClassDivision.class_level == class_level,
                ClassDivision.division == division,
                ClassDivision.data_origin == "DEMO",
            )
            .filter(
                ClassDivision.school.has(
                    school_code=school_code
                )
            )
            .first()
        )

        assert class_division is not None

        return class_division.id
    finally:
        db.close()


def cleanup_student(student_code: str):
    db = SessionLocal()

    try:
        student = (
            db.query(Student)
            .filter(Student.student_code == student_code)
            .first()
        )

        if student and student.data_origin != "DEMO":
            db.delete(student)
            db.commit()
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Test users
# ---------------------------------------------------------------------------

DATA_MANAGER_EMAIL = "dm001@demo.vigyan.com"
PT001_EMAIL = "pt001@demo.vigyan.com"

DATA_MANAGER_TOKEN = None
PT001_TOKEN = None


@pytest.fixture(scope="module")
def data_manager_token():
    global DATA_MANAGER_TOKEN

    if DATA_MANAGER_TOKEN is None:
        DATA_MANAGER_TOKEN = login(DATA_MANAGER_EMAIL)

    return DATA_MANAGER_TOKEN


@pytest.fixture(scope="module")
def pt001_token():
    global PT001_TOKEN

    if PT001_TOKEN is None:
        PT001_TOKEN = login(PT001_EMAIL)

    return PT001_TOKEN


# ---------------------------------------------------------------------------
# CREATE TESTS
# ---------------------------------------------------------------------------

def test_data_manager_can_create_student(data_manager_token):
    student_code = "CRUDSTU001"

    cleanup_student(student_code)

    class_division_id = get_demo_class_division(
        "PVS",
        5,
        "A",
    )

    response = client.post(
        "/api/v1/students",
        headers=auth_headers(data_manager_token),
        json={
            "student_code": student_code,
            "full_name": "CRUD Test Student",
            "gender": "Female",
            "roll_no": 900,
            "class_division_id": str(class_division_id),
            "status": "ACTIVE",
        },
    )

    assert response.status_code == 201, response.text

    data = response.json()

    assert data["student_code"] == student_code
    assert data["full_name"] == "CRUD Test Student"
    assert data["gender"] == "Female"
    assert data["roll_no"] == 900
    assert data["class_division_id"] == str(class_division_id)
    assert data["status"] == "ACTIVE"

    # Server must control data_origin.
    assert data["data_origin"] == "PRODUCTION"

    cleanup_student(student_code)


def test_para_teacher_cannot_create_student(pt001_token):
    student_code = "CRUDSTU002"

    cleanup_student(student_code)

    class_division_id = get_demo_class_division(
        "PVS",
        5,
        "A",
    )

    response = client.post(
        "/api/v1/students",
        headers=auth_headers(pt001_token),
        json={
            "student_code": student_code,
            "full_name": "Unauthorized Student",
            "gender": "Male",
            "roll_no": 901,
            "class_division_id": str(class_division_id),
            "status": "ACTIVE",
        },
    )

    assert response.status_code == 403

    cleanup_student(student_code)


def test_create_student_with_nonexistent_class_division(
    data_manager_token,
):
    fake_class_division_id = str(
        UUID("00000000-0000-0000-0000-000000000001")
    )

    response = client.post(
        "/api/v1/students",
        headers=auth_headers(data_manager_token),
        json={
            "student_code": "CRUDSTU003",
            "full_name": "Missing Class Student",
            "gender": "Male",
            "roll_no": 902,
            "class_division_id": fake_class_division_id,
            "status": "ACTIVE",
        },
    )

    assert response.status_code == 404


def test_create_student_in_unauthorized_school(
    pt001_token,
):
    # NLS belongs to PT002, not PT001.
    class_division_id = get_demo_class_division(
        "NLS",
        5,
        "B",
    )

    response = client.post(
        "/api/v1/students",
        headers=auth_headers(pt001_token),
        json={
            "student_code": "CRUDSTU004",
            "full_name": "Unauthorized School Student",
            "gender": "Male",
            "roll_no": 903,
            "class_division_id": str(class_division_id),
            "status": "ACTIVE",
        },
    )

    assert response.status_code == 403

    cleanup_student("CRUDSTU004")


def test_duplicate_student_code_returns_409(
    data_manager_token,
):
    student_code = "CRUDSTU005"

    cleanup_student(student_code)

    class_division_id = get_demo_class_division(
        "PVS",
        5,
        "A",
    )

    payload = {
        "student_code": student_code,
        "full_name": "Duplicate Code Student",
        "gender": "Male",
        "roll_no": 904,
        "class_division_id": str(class_division_id),
        "status": "ACTIVE",
    }

    first_response = client.post(
        "/api/v1/students",
        headers=auth_headers(data_manager_token),
        json=payload,
    )

    assert first_response.status_code == 201, first_response.text

    second_response = client.post(
        "/api/v1/students",
        headers=auth_headers(data_manager_token),
        json=payload,
    )

    assert second_response.status_code == 409

    cleanup_student(student_code)


def test_duplicate_roll_number_returns_409(
    data_manager_token,
):
    first_code = "CRUDSTU006"
    second_code = "CRUDSTU007"

    cleanup_student(first_code)
    cleanup_student(second_code)

    class_division_id = get_demo_class_division(
        "PVS",
        5,
        "A",
    )

    first_response = client.post(
        "/api/v1/students",
        headers=auth_headers(data_manager_token),
        json={
            "student_code": first_code,
            "full_name": "First Roll Student",
            "gender": "Male",
            "roll_no": 905,
            "class_division_id": str(class_division_id),
            "status": "ACTIVE",
        },
    )

    assert first_response.status_code == 201, first_response.text

    second_response = client.post(
        "/api/v1/students",
        headers=auth_headers(data_manager_token),
        json={
            "student_code": second_code,
            "full_name": "Second Roll Student",
            "gender": "Female",
            "roll_no": 905,
            "class_division_id": str(class_division_id),
            "status": "ACTIVE",
        },
    )

    assert second_response.status_code == 409

    cleanup_student(first_code)
    cleanup_student(second_code)


def test_data_origin_is_server_controlled(
    data_manager_token,
):
    student_code = "CRUDSTU008"

    cleanup_student(student_code)

    class_division_id = get_demo_class_division(
        "PVS",
        5,
        "A",
    )

    response = client.post(
        "/api/v1/students",
        headers=auth_headers(data_manager_token),
        json={
            "student_code": student_code,
            "full_name": "Origin Test Student",
            "gender": "Female",
            "roll_no": 906,
            "class_division_id": str(class_division_id),
            "status": "ACTIVE",
            "data_origin": "DEMO",
        },
    )

    assert response.status_code == 201, response.text
    assert response.json()["data_origin"] == "PRODUCTION"

    cleanup_student(student_code)


# ---------------------------------------------------------------------------
# UPDATE TESTS
# ---------------------------------------------------------------------------

@pytest.fixture
def created_student(data_manager_token):
    student_code = "CRUDSTU009"

    cleanup_student(student_code)

    class_division_id = get_demo_class_division(
        "PVS",
        5,
        "A",
    )

    response = client.post(
        "/api/v1/students",
        headers=auth_headers(data_manager_token),
        json={
            "student_code": student_code,
            "full_name": "Original Student",
            "gender": "Male",
            "roll_no": 907,
            "class_division_id": str(class_division_id),
            "status": "ACTIVE",
        },
    )

    assert response.status_code == 201, response.text

    student = response.json()

    yield student

    cleanup_student(student_code)


def test_data_manager_can_update_full_name(
    data_manager_token,
    created_student,
):
    student_id = created_student["id"]

    response = client.patch(
        f"/api/v1/students/{student_id}",
        headers=auth_headers(data_manager_token),
        json={
            "full_name": "Updated Student Name",
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["full_name"] == "Updated Student Name"


def test_data_manager_can_update_gender(
    data_manager_token,
    created_student,
):
    student_id = created_student["id"]

    response = client.patch(
        f"/api/v1/students/{student_id}",
        headers=auth_headers(data_manager_token),
        json={
            "gender": "Female",
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["gender"] == "Female"


def test_data_manager_can_update_roll_no(
    data_manager_token,
    created_student,
):
    student_id = created_student["id"]

    response = client.patch(
        f"/api/v1/students/{student_id}",
        headers=auth_headers(data_manager_token),
        json={
            "roll_no": 908,
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["roll_no"] == 908


def test_data_manager_can_update_status(
    data_manager_token,
    created_student,
):
    student_id = created_student["id"]

    response = client.patch(
        f"/api/v1/students/{student_id}",
        headers=auth_headers(data_manager_token),
        json={
            "status": "INACTIVE",
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "INACTIVE"


def test_para_teacher_cannot_update_student(
    pt001_token,
    created_student,
):
    student_id = created_student["id"]

    response = client.patch(
        f"/api/v1/students/{student_id}",
        headers=auth_headers(pt001_token),
        json={
            "full_name": "Unauthorized Update",
        },
    )

    assert response.status_code == 403


def test_update_nonexistent_student_returns_404(
    data_manager_token,
):
    fake_student_id = "00000000-0000-0000-0000-000000000001"

    response = client.patch(
        f"/api/v1/students/{fake_student_id}",
        headers=auth_headers(data_manager_token),
        json={
            "full_name": "Missing Student",
        },
    )

    assert response.status_code == 404


def test_para_teacher_cannot_update_student_in_unauthorized_school(
    pt001_token,
):
    # Create a temporary NLS student as Data Manager.
    student_code = "CRUDSTU010"

    cleanup_student(student_code)

    class_division_id = get_demo_class_division(
        "NLS",
        5,
        "B",
    )

    data_manager_token = login(DATA_MANAGER_EMAIL)

    create_response = client.post(
        "/api/v1/students",
        headers=auth_headers(data_manager_token),
        json={
            "student_code": student_code,
            "full_name": "NLS Test Student",
            "gender": "Male",
            "roll_no": 909,
            "class_division_id": str(class_division_id),
            "status": "ACTIVE",
        },
    )

    assert create_response.status_code == 201, create_response.text

    student_id = create_response.json()["id"]

    response = client.patch(
        f"/api/v1/students/{student_id}",
        headers=auth_headers(pt001_token),
        json={
            "full_name": "Unauthorized NLS Update",
        },
    )

    assert response.status_code == 403

    cleanup_student(student_code)


def test_empty_update_returns_400(
    data_manager_token,
    created_student,
):
    student_id = created_student["id"]

    response = client.patch(
        f"/api/v1/students/{student_id}",
        headers=auth_headers(data_manager_token),
        json={},
    )

    assert response.status_code == 400


def test_duplicate_roll_number_on_update_returns_409(
    data_manager_token,
    created_student,
):
    second_code = "CRUDSTU011"

    cleanup_student(second_code)

    class_division_id = UUID(
        created_student["class_division_id"]
    )

    create_response = client.post(
        "/api/v1/students",
        headers=auth_headers(data_manager_token),
        json={
            "student_code": second_code,
            "full_name": "Second Update Student",
            "gender": "Female",
            "roll_no": 910,
            "class_division_id": str(class_division_id),
            "status": "ACTIVE",
        },
    )

    assert create_response.status_code == 201, create_response.text

    student_id = created_student["id"]

    response = client.patch(
        f"/api/v1/students/{student_id}",
        headers=auth_headers(data_manager_token),
        json={
            "roll_no": 910,
        },
    )

    assert response.status_code == 409

    cleanup_student(second_code)


# ---------------------------------------------------------------------------
# IMMUTABILITY TESTS
# ---------------------------------------------------------------------------

def test_student_code_cannot_be_changed(
    data_manager_token,
    created_student,
):
    student_id = created_student["id"]

    response = client.patch(
        f"/api/v1/students/{student_id}",
        headers=auth_headers(data_manager_token),
        json={
            "student_code": "CHANGEDCODE",
        },
    )

    assert response.status_code == 400

    # Verify the original value is unchanged.
    get_response = client.get(
        f"/api/v1/students/{student_id}",
        headers=auth_headers(data_manager_token),
    )

    assert get_response.status_code == 200
    assert (
        get_response.json()["student_code"]
        == created_student["student_code"]
    )


def test_class_division_id_cannot_be_changed(
    data_manager_token,
    created_student,
):
    student_id = created_student["id"]

    another_class_division_id = get_demo_class_division(
        "PVS",
        6,
        "C",
    )

    response = client.patch(
        f"/api/v1/students/{student_id}",
        headers=auth_headers(data_manager_token),
        json={
            "class_division_id": str(
                another_class_division_id
            ),
        },
    )

    assert response.status_code == 400

    # Verify the original class division is unchanged.
    get_response = client.get(
        f"/api/v1/students/{student_id}",
        headers=auth_headers(data_manager_token),
    )

    assert get_response.status_code == 200
    assert (
        get_response.json()["class_division_id"]
        == created_student["class_division_id"]
    )


def test_data_origin_cannot_be_changed(
    data_manager_token,
    created_student,
):
    student_id = created_student["id"]

    response = client.patch(
        f"/api/v1/students/{student_id}",
        headers=auth_headers(data_manager_token),
        json={
            "data_origin": "DEMO",
        },
    )

    assert response.status_code == 400

    # Verify data_origin remains server-controlled.
    get_response = client.get(
        f"/api/v1/students/{student_id}",
        headers=auth_headers(data_manager_token),
    )

    assert get_response.status_code == 200
    assert get_response.json()["data_origin"] == "PRODUCTION"
# ---------------------------------------------------------------------------
# REGRESSION / DEMO DATA SAFETY
# ---------------------------------------------------------------------------

def test_demo_student_counts_remain_unchanged():
    db = SessionLocal()

    try:
        counts = {}

        for school_code in ["PVS", "NLS", "SHY", "UECL"]:
            count = (
                db.query(Student)
                .join(Student.class_division)
                .join(ClassDivision.school)
                .filter(
                    ClassDivision.school.has(
                        school_code=school_code
                    ),
                    Student.data_origin == "DEMO",
                )
                .count()
            )

            counts[school_code] = count

        assert counts == {
            "PVS": 255,
            "NLS": 76,
            "SHY": 194,
            "UECL": 55,
        }

    finally:
        db.close()
