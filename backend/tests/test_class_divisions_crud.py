import os
from uuid import UUID

from app.database import SessionLocal
from app.models import ClassDivision
import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient

from app.main import app


load_dotenv()

DEMO_PASSWORD = os.getenv("DEMO_USER_PASSWORD")

if not DEMO_PASSWORD:
    raise RuntimeError(
        "DEMO_USER_PASSWORD must be configured in .env "
        "before running class division CRUD tests."
    )


client = TestClient(app)


PARA_TEACHERS = [
    "pt001@demo.vigyan.com",
    "pt002@demo.vigyan.com",
    "pt003@demo.vigyan.com",
    "pt004@demo.vigyan.com",
]

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


def get_first_school(token: str) -> dict:
    response = client.get(
        "/api/v1/schools",
        headers=auth_headers(token),
    )

    assert response.status_code == 200, response.text
    schools = response.json()

    assert schools

    return schools[0]


def get_first_class_division(token: str) -> dict:
    response = client.get(
        "/api/v1/class-divisions",
        headers=auth_headers(token),
    )

    assert response.status_code == 200, response.text
    divisions = response.json()

    assert divisions

    return divisions[0]

def delete_class_division(class_division_id: str) -> None:
    db = SessionLocal()

    try:
        class_division = (
            db.query(ClassDivision)
            .filter(ClassDivision.id == UUID(class_division_id))
            .first()
        )

        if class_division:
            db.delete(class_division)
            db.commit()
    finally:
        db.close()

@pytest.mark.parametrize(
    "email",
    PARA_TEACHERS,
)
def test_para_teacher_cannot_create_class_division(email):
    """
    Para-Teachers must not create class divisions.
    """

    token = login(email)
    school = get_first_school(token)

    response = client.post(
        "/api/v1/class-divisions",
        headers=auth_headers(token),
        json={
            "school_id": school["id"],
            "class_level": 5,
            "division": "TEST",
            "status": "ACTIVE",
        },
    )

    assert response.status_code == 403

    assert response.json()["detail"] == (
        "You do not have permission to perform this action."
    )


@pytest.mark.parametrize(
    "email",
    PARA_TEACHERS,
)
def test_para_teacher_cannot_update_class_division(email):
    """
    Para-Teachers must not update class divisions.
    """

    token = login(email)
    class_division = get_first_class_division(token)

    response = client.patch(
        f"/api/v1/class-divisions/{class_division['id']}",
        headers=auth_headers(token),
        json={
            "division": "UNAUTHORIZED",
        },
    )

    assert response.status_code == 403

    assert response.json()["detail"] == (
        "You do not have permission to perform this action."
    )


def test_create_class_division_requires_authentication():
    """
    Class division creation must require authentication.
    """

    response = client.post(
        "/api/v1/class-divisions",
        json={
            "school_id": "00000000-0000-0000-0000-000000000000",
            "class_level": 5,
            "division": "TEST",
            "status": "ACTIVE",
        },
    )

    assert response.status_code == 401


def test_update_class_division_requires_authentication():
    """
    Class division update must require authentication.
    """

    response = client.patch(
        "/api/v1/class-divisions/"
        "00000000-0000-0000-0000-000000000000",
        json={
            "division": "TEST",
        },
    )

    assert response.status_code == 401


def test_data_manager_can_create_class_division():
    """
    Data Manager can create a production class division.
    """

    token = login(DATA_MANAGER)
    school = get_first_school(token)

    response = client.post(
        "/api/v1/class-divisions",
        headers=auth_headers(token),
        json={
            "school_id": school["id"],
            "class_level": 5,
            "division": "CRUDTEST",
            "status": "ACTIVE",
        },
    )

    assert response.status_code == 201, response.text

    data = response.json()

    assert data["school_id"] == school["id"]
    assert data["class_level"] == 5
    assert data["division"] == "CRUDTEST"
    assert data["status"] == "ACTIVE"
    assert data["data_origin"] == "PRODUCTION"

    class_division_id = data["id"]

    delete_class_division(class_division_id)

def test_duplicate_class_division_returns_conflict():
    """
    Duplicate school/class/division combinations must be rejected.
    """

    token = login(DATA_MANAGER)
    school = get_first_school(token)

    division = "DUPTEST"

    first = client.post(
        "/api/v1/class-divisions",
        headers=auth_headers(token),
        json={
            "school_id": school["id"],
            "class_level": 5,
            "division": division,
        },
    )

    assert first.status_code == 201, first.text

    second = client.post(
        "/api/v1/class-divisions",
        headers=auth_headers(token),
        json={
            "school_id": school["id"],
            "class_level": 5,
            "division": division,
        },
    )

    assert second.status_code == 409

    assert second.json()["detail"] == (
        "A class division with the same school, "
        "class level, and division already exists."
    )
    delete_class_division(first.json()["id"])


@pytest.mark.parametrize(
    "class_level",
    [4, 8, 0, 10],
)
def test_invalid_class_level_is_rejected(class_level):
    """
    Only classes 5, 6, and 7 are supported.
    """

    token = login(DATA_MANAGER)
    school = get_first_school(token)

    response = client.post(
        "/api/v1/class-divisions",
        headers=auth_headers(token),
        json={
            "school_id": school["id"],
            "class_level": class_level,
            "division": "INVALID",
        },
    )

    assert response.status_code == 422


@pytest.mark.parametrize(
    "status_value",
    ["INVALID", "", "ACTIVE123"],
)
def test_invalid_class_division_status_is_rejected(status_value):
    """
    Only ACTIVE and INACTIVE are valid statuses.
    """

    token = login(DATA_MANAGER)
    school = get_first_school(token)

    response = client.post(
        "/api/v1/class-divisions",
        headers=auth_headers(token),
        json={
            "school_id": school["id"],
            "class_level": 5,
            "division": "STATUS",
            "status": status_value,
        },
    )

    assert response.status_code == 422


def test_empty_division_is_rejected():
    """
    Division cannot be empty or whitespace.
    """

    token = login(DATA_MANAGER)
    school = get_first_school(token)

    response = client.post(
        "/api/v1/class-divisions",
        headers=auth_headers(token),
        json={
            "school_id": school["id"],
            "class_level": 5,
            "division": "   ",
        },
    )

    assert response.status_code == 422


def test_unknown_school_returns_not_found():
    """
    Creating a class division under an unknown school must fail.
    """

    token = login(DATA_MANAGER)

    response = client.post(
        "/api/v1/class-divisions",
        headers=auth_headers(token),
        json={
            "school_id": "00000000-0000-0000-0000-000000000000",
            "class_level": 5,
            "division": "UNKNOWN",
        },
    )

    assert response.status_code == 404

    assert response.json()["detail"] == "School not found."


def test_data_manager_can_update_class_division():
    """
    Data Manager can update mutable class division fields.
    """

    token = login(DATA_MANAGER)
    school = get_first_school(token)

    create_response = client.post(
        "/api/v1/class-divisions",
        headers=auth_headers(token),
        json={
            "school_id": school["id"],
            "class_level": 5,
            "division": "UPDATETEST",
            "status": "ACTIVE",
        },
    )

    assert create_response.status_code == 201, create_response.text

    class_division = create_response.json()

    try:
        response = client.patch(
            f"/api/v1/class-divisions/{class_division['id']}",
            headers=auth_headers(token),
            json={
                "status": "INACTIVE",
            },
        )

        assert response.status_code == 200, response.text

        data = response.json()

        assert data["status"] == "INACTIVE"
        assert data["division"] == "UPDATETEST"
    finally:
        delete_class_division(class_division["id"])


def test_empty_class_division_update_is_rejected():
    """
    An empty PATCH request must be rejected.
    """

    token = login(DATA_MANAGER)

    class_division = get_first_class_division(token)

    response = client.patch(
        f"/api/v1/class-divisions/{class_division['id']}",
        headers=auth_headers(token),
        json={},
    )

    assert response.status_code == 400

    assert response.json()["detail"] == (
        "No fields provided for update."
    )

def test_class_division_school_is_immutable():
    """
    school_id cannot be changed through the update endpoint.
    """

    token = login(DATA_MANAGER)

    class_division = get_first_class_division(token)

    response = client.patch(
        f"/api/v1/class-divisions/{class_division['id']}",
        headers=auth_headers(token),
        json={
            "school_id": "00000000-0000-0000-0000-000000000000",
        },
    )

    # The field is not part of the update schema, so Pydantic
    # ignores it and the endpoint sees no valid update fields.
    assert response.status_code == 400


def test_class_division_level_is_immutable():
    """
    class_level cannot be changed through the update endpoint.
    """

    token = login(DATA_MANAGER)

    class_division = get_first_class_division(token)

    response = client.patch(
        f"/api/v1/class-divisions/{class_division['id']}",
        headers=auth_headers(token),
        json={
            "class_level": 7,
        },
    )

    assert response.status_code == 400


def test_class_division_data_origin_is_server_controlled():
    """
    Clients cannot manipulate data_origin.
    """

    token = login(DATA_MANAGER)
    school = get_first_school(token)

    response = client.post(
        "/api/v1/class-divisions",
        headers=auth_headers(token),
        json={
            "school_id": school["id"],
            "class_level": 6,
            "division": "ORIGINTEST",
            "status": "ACTIVE",
            "data_origin": "DEMO",
        },
    )

    assert response.status_code == 201, response.text

    data = response.json()

    assert data["data_origin"] == "PRODUCTION"

    delete_class_division(data["id"])
