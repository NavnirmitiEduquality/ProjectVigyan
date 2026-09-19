import os
from uuid import UUID

import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient

from app.main import app


load_dotenv()

DEMO_PASSWORD = os.getenv("DEMO_USER_PASSWORD")

if not DEMO_PASSWORD:
    raise RuntimeError(
        "DEMO_USER_PASSWORD must be configured in .env "
        "before running authorization tests."
    )


client = TestClient(app)


PARA_TEACHERS = {
    "PT001": {
        "email": "pt001@demo.vigyan.com",
        "school_code": "PVS",
        "school_name": "Pragati Vidya School",
    },
    "PT002": {
        "email": "pt002@demo.vigyan.com",
        "school_code": "NLS",
        "school_name": "Navnirmiti Learning School",
    },
    "PT003": {
        "email": "pt003@demo.vigyan.com",
        "school_code": "SHY",
        "school_name": "Sahyadri",
    },
    "PT004": {
        "email": "pt004@demo.vigyan.com",
        "school_code": "UECL",
        "school_name": "Udaan Education Centre for Learning",
    },
}


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


def get_school_ids(token: str) -> dict[str, UUID]:
    response = client.get(
        "/api/v1/schools",
        headers=auth_headers(token),
    )

    assert response.status_code == 200, response.text

    schools = response.json()

    return {
        school["school_code"]: UUID(school["id"])
        for school in schools
    }


@pytest.mark.parametrize(
    "user_code",
    ["PT001", "PT002", "PT003", "PT004"],
)
def test_para_teacher_sees_only_assigned_school(user_code):
    """
    Every Para-Teacher must see exactly their assigned school.
    """

    user = PARA_TEACHERS[user_code]

    token = login(user["email"])

    response = client.get(
        "/api/v1/schools",
        headers=auth_headers(token),
    )

    assert response.status_code == 200, response.text

    schools = response.json()

    assert len(schools) == 1

    assert schools[0]["school_code"] == user["school_code"]

    assert schools[0]["school_name"] == user["school_name"]


@pytest.mark.parametrize(
    "user_code",
    ["PT001", "PT002", "PT003", "PT004"],
)
def test_para_teacher_student_scope(user_code):
    """
    A Para-Teacher must only receive students from their assigned school.
    """

    user = PARA_TEACHERS[user_code]

    token = login(user["email"])

    response = client.get(
        "/api/v1/students",
        headers=auth_headers(token),
    )

    assert response.status_code == 200, response.text

    students = response.json()

    expected_counts = {
        "PVS": 255,
        "NLS": 76,
        "SHY": 194,
        "UECL": 55,
    }

    assert len(students) == expected_counts[user["school_code"]]

    # Student codes begin with their school code.
    assert all(
        student["student_code"].startswith(user["school_code"])
        for student in students
    )


def test_para_teacher_cannot_access_other_school():
    """
    PT001 must not access NLS directly by school ID.
    """

    token = login(
        PARA_TEACHERS["PT001"]["email"]
    )

    schools_response = client.get(
        "/api/v1/schools",
        headers=auth_headers(token),
    )

    assert schools_response.status_code == 200

    # We need the NLS ID independently.
    # Use PT002's authorized response.
    nls_token = login(
        PARA_TEACHERS["PT002"]["email"]
    )

    nls_response = client.get(
        "/api/v1/schools",
        headers=auth_headers(nls_token),
    )

    assert nls_response.status_code == 200

    nls_school = nls_response.json()[0]
    nls_id = nls_school["id"]

    forbidden_response = client.get(
        f"/api/v1/schools/{nls_id}",
        headers=auth_headers(token),
    )

    assert forbidden_response.status_code == 403

    assert forbidden_response.json()["detail"] == (
        "You are not authorized to access this school."
    )


def test_para_teacher_cannot_bypass_scope_with_school_filter():
    """
    PT001 must not retrieve NLS students by manipulating
    the school_id query parameter.
    """

    pt001_token = login(
        PARA_TEACHERS["PT001"]["email"]
    )

    pt002_token = login(
        PARA_TEACHERS["PT002"]["email"]
    )

    nls_response = client.get(
        "/api/v1/schools",
        headers=auth_headers(pt002_token),
    )

    assert nls_response.status_code == 200

    nls_id = nls_response.json()[0]["id"]

    response = client.get(
        f"/api/v1/students?school_id={nls_id}",
        headers=auth_headers(pt001_token),
    )

    assert response.status_code == 403

    assert response.json()["detail"] == (
        "You are not authorized to access this school."
    )


@pytest.mark.parametrize(
    "user_code",
    ["PT001", "PT002", "PT003", "PT004"],
)
def test_para_teacher_class_division_scope(user_code):
    """
    A Para-Teacher must only receive class divisions
    belonging to their assigned school.
    """

    user = PARA_TEACHERS[user_code]

    token = login(user["email"])

    response = client.get(
        "/api/v1/class-divisions",
        headers=auth_headers(token),
    )

    assert response.status_code == 200, response.text

    divisions = response.json()

    assert len(divisions) == 3

    expected_divisions = {
        "PVS": {
            (5, "A"),
            (6, "C"),
            (7, "B"),
        },
        "NLS": {
            (5, "B"),
            (6, "A"),
            (7, "C"),
        },
        "SHY": {
            (5, "C"),
            (6, "B"),
            (7, "A"),
        },
        "UECL": {
            (5, "A"),
            (6, "C"),
            (7, "B"),
        },
    }

    actual = {
        (
            division["class_level"],
            division["division"],
        )
        for division in divisions
    }

    assert actual == expected_divisions[
        user["school_code"]
    ]


def test_para_teacher_cannot_access_other_school_class_division():
    """
    PT001 must not access an NLS class division directly.
    """

    pt001_token = login(
        PARA_TEACHERS["PT001"]["email"]
    )

    nls_token = login(
        PARA_TEACHERS["PT002"]["email"]
    )

    nls_response = client.get(
        "/api/v1/class-divisions",
        headers=auth_headers(nls_token),
    )

    assert nls_response.status_code == 200

    nls_class_division_id = nls_response.json()[0]["id"]

    response = client.get(
        f"/api/v1/class-divisions/{nls_class_division_id}",
        headers=auth_headers(pt001_token),
    )

    assert response.status_code == 403


def test_para_teacher_cannot_access_other_school_student():
    """
    PT001 must not access an NLS student directly.
    """

    pt001_token = login(
        PARA_TEACHERS["PT001"]["email"]
    )

    nls_token = login(
        PARA_TEACHERS["PT002"]["email"]
    )

    nls_response = client.get(
        "/api/v1/students",
        headers=auth_headers(nls_token),
    )

    assert nls_response.status_code == 200

    nls_student_id = nls_response.json()[0]["id"]

    response = client.get(
        f"/api/v1/students/{nls_student_id}",
        headers=auth_headers(pt001_token),
    )

    assert response.status_code == 403
