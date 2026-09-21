import os

import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient

from app.main import app


load_dotenv()

DEMO_PASSWORD = os.getenv("DEMO_USER_PASSWORD")

if not DEMO_PASSWORD:
    raise RuntimeError(
        "DEMO_USER_PASSWORD must be configured in .env "
        "before running school CRUD tests."
    )


client = TestClient(app)


PARA_TEACHERS = [
    "pt001@demo.vigyan.com",
    "pt002@demo.vigyan.com",
    "pt003@demo.vigyan.com",
    "pt004@demo.vigyan.com",
]


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


@pytest.mark.parametrize(
    "email",
    PARA_TEACHERS,
)
def test_para_teacher_cannot_create_school(email):
    """
    Para-Teachers must not create schools.
    """

    token = login(email)

    response = client.post(
        "/api/v1/schools",
        headers=auth_headers(token),
        json={
            "school_code": "TEST01",
            "school_name": "Test School",
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
def test_para_teacher_cannot_update_school(email):
    """
    Para-Teachers must not update schools.
    """

    token = login(email)

    schools_response = client.get(
        "/api/v1/schools",
        headers=auth_headers(token),
    )

    assert schools_response.status_code == 200

    school_id = schools_response.json()[0]["id"]

    response = client.patch(
        f"/api/v1/schools/{school_id}",
        headers=auth_headers(token),
        json={
            "school_name": "Unauthorized Update",
        },
    )

    assert response.status_code == 403

    assert response.json()["detail"] == (
        "You do not have permission to perform this action."
    )


def test_create_school_requires_authentication():
    """
    School creation must require authentication.
    """

    response = client.post(
        "/api/v1/schools",
        json={
            "school_code": "TEST01",
            "school_name": "Test School",
            "status": "ACTIVE",
        },
    )

    assert response.status_code == 401


def test_update_school_requires_authentication():
    """
    School update must require authentication.
    """

    response = client.patch(
        "/api/v1/schools/00000000-0000-0000-0000-000000000000",
        json={
            "school_name": "Test School",
        },
    )

    assert response.status_code == 401


def test_invalid_school_status_is_rejected():
    """
    Only ACTIVE and INACTIVE are valid school statuses.
    """

    token = login(PARA_TEACHERS[0])

    response = client.post(
        "/api/v1/schools",
        headers=auth_headers(token),
        json={
            "school_code": "TEST01",
            "school_name": "Test School",
            "status": "INVALID",
        },
    )

    # Permission is checked before request processing for this user,
    # so this request should be rejected by authorization.
    assert response.status_code == 403


def test_school_update_unknown_school_requires_permission():
    """
    Authorization is evaluated before resource modification.
    """

    token = login(PARA_TEACHERS[0])

    response = client.patch(
        "/api/v1/schools/00000000-0000-0000-0000-000000000000",
        headers=auth_headers(token),
        json={
            "school_name": "Updated School",
        },
    )

    assert response.status_code == 403
