from datetime import date
import os

import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models import (
    ClassDivision,
    SessionPlanContent,
    SessionPlanItem,
    SessionPlanWeek,
    User,
)


load_dotenv()

DEMO_PASSWORD = os.getenv("DEMO_USER_PASSWORD")

if not DEMO_PASSWORD:
    raise RuntimeError(
        "DEMO_USER_PASSWORD must be configured in .env "
        "before running session plan CRUD tests."
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


def _cleanup_session_plan_state():
    db = SessionLocal()

    try:
        para_teacher_emails = [
            config["email"]
            for config in PARA_TEACHERS.values()
        ]

        para_teacher_ids = (
            db.query(User.id)
            .filter(User.email.in_(para_teacher_emails))
            .subquery()
        )

        weeks = (
            db.query(SessionPlanWeek)
            .filter(
                SessionPlanWeek.para_teacher_id.in_(
                    para_teacher_ids
                )
            )
            .all()
        )

        if not weeks:
            return

        week_ids = [week.id for week in weeks]

        items = (
            db.query(SessionPlanItem)
            .filter(
                SessionPlanItem.session_plan_week_id.in_(
                    week_ids
                )
            )
            .all()
        )

        item_ids = [item.id for item in items]

        if item_ids:
            contents = (
                db.query(SessionPlanContent)
                .filter(
                    SessionPlanContent.session_plan_item_id.in_(
                        item_ids
                    )
                )
                .all()
            )

            for content in contents:
                db.delete(content)

        for item in items:
            db.delete(item)

        for week in weeks:
            db.delete(week)

        db.commit()

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


@pytest.fixture(autouse=True)
def clean_session_plan_state():
    """
    Keep session-plan CRUD tests isolated when running against
    the persistent demo database.
    """
    _cleanup_session_plan_state()

    yield

    _cleanup_session_plan_state()


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


def get_user_id_by_email(email: str) -> str:
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


def create_week(
    token: str,
    week_start_date: str = "2026-09-21",
) -> dict:
    response = client.post(
        "/api/v1/session-plans/weeks",
        headers=auth_headers(token),
        json={
            "week_start_date": week_start_date,
        },
    )

    assert response.status_code == 201, response.text

    return response.json()


def create_item(
    token: str,
    week_id: str,
    class_division_id: str,
    *,
    planned_date: str = "2026-09-21",
    sequence_no: int = 1,
    planned_start_time: str | None = None,
    planned_end_time: str | None = None,
) -> dict:
    payload = {
        "session_plan_week_id": week_id,
        "class_division_id": class_division_id,
        "planned_date": planned_date,
        "sequence_no": sequence_no,
    }

    if planned_start_time is not None:
        payload["planned_start_time"] = planned_start_time

    if planned_end_time is not None:
        payload["planned_end_time"] = planned_end_time

    response = client.post(
        "/api/v1/session-plans/items",
        headers=auth_headers(token),
        json=payload,
    )

    assert response.status_code == 201, response.text

    return response.json()


# ----------------------------------------------------------------------
# WEEK CREATION / RETRIEVAL
# ----------------------------------------------------------------------


def test_session_plan_week_creation_requires_authentication():
    response = client.post(
        "/api/v1/session-plans/weeks",
        json={
            "week_start_date": "2026-09-21",
        },
    )

    assert response.status_code == 401


@pytest.mark.parametrize(
    "user_code",
    ["PT001", "PT002", "PT003", "PT004"],
)
def test_para_teacher_can_create_session_plan_week(user_code):
    """
    A Para-Teacher can create a planning week for their own
    authenticated planning scope.
    """

    user = PARA_TEACHERS[user_code]

    token = login(user["email"])

    response = client.post(
        "/api/v1/session-plans/weeks",
        headers=auth_headers(token),
        json={
            "week_start_date": "2026-09-21",
        },
    )

    assert response.status_code == 201, response.text

    data = response.json()

    authenticated_user_id = get_user_id_by_email(
        user["email"]
    )

    assert data["para_teacher_id"] == authenticated_user_id
    assert data["week_start_date"] == "2026-09-21"
    assert data["week_end_date"] == "2026-09-27"
    assert data["data_origin"] == "PRODUCTION"
    assert data["id"] is not None
    assert data["created_at"] is not None
    assert data["updated_at"] is not None


def test_client_cannot_control_week_owner():
    """
    The authenticated user is always the planning-week owner.
    """

    token = login(
        PARA_TEACHERS["PT001"]["email"]
    )

    response = client.post(
        "/api/v1/session-plans/weeks",
        headers=auth_headers(token),
        json={
            "week_start_date": "2026-09-21",
            "para_teacher_id": (
                "00000000-0000-0000-0000-000000000001"
            ),
        },
    )

    assert response.status_code == 201, response.text

    data = response.json()

    authenticated_user_id = get_user_id_by_email(
        PARA_TEACHERS["PT001"]["email"]
    )

    assert data["para_teacher_id"] == authenticated_user_id


def test_client_cannot_control_week_data_origin():
    """
    Production API records must remain PRODUCTION.
    """

    token = login(
        PARA_TEACHERS["PT001"]["email"]
    )

    response = client.post(
        "/api/v1/session-plans/weeks",
        headers=auth_headers(token),
        json={
            "week_start_date": "2026-09-21",
            "data_origin": "DEMO",
        },
    )

    assert response.status_code == 201, response.text

    assert response.json()["data_origin"] == "PRODUCTION"


@pytest.mark.parametrize(
    "week_start_date",
    [
        "2026-09-22",  # Tuesday
        "2026-09-23",  # Wednesday
        "2026-09-24",  # Thursday
        "2026-09-25",  # Friday
        "2026-09-26",  # Saturday
        "2026-09-27",  # Sunday
    ],
)
def test_non_monday_week_is_rejected(week_start_date):
    """
    Planning weeks must start on Monday.
    """

    token = login(
        PARA_TEACHERS["PT001"]["email"]
    )

    response = client.post(
        "/api/v1/session-plans/weeks",
        headers=auth_headers(token),
        json={
            "week_start_date": week_start_date,
        },
    )

    assert response.status_code == 400, response.text


def test_duplicate_week_returns_existing_week():
    """
    The router uses get_or_create semantics.

    Creating the same authenticated-user/week combination
    again must return the existing planning week.
    """

    token = login(
        PARA_TEACHERS["PT001"]["email"]
    )

    first_response = client.post(
        "/api/v1/session-plans/weeks",
        headers=auth_headers(token),
        json={
            "week_start_date": "2026-09-21",
        },
    )

    assert first_response.status_code == 201

    second_response = client.post(
        "/api/v1/session-plans/weeks",
        headers=auth_headers(token),
        json={
            "week_start_date": "2026-09-21",
        },
    )

    assert second_response.status_code == 201

    first = first_response.json()
    second = second_response.json()

    assert second["id"] == first["id"]
    assert second["para_teacher_id"] == first["para_teacher_id"]
    assert second["week_start_date"] == first["week_start_date"]
    assert second["week_end_date"] == first["week_end_date"]


def test_get_session_plan_week_requires_authentication():
    response = client.get(
        "/api/v1/session-plans/weeks/2026-09-21"
    )

    assert response.status_code == 401


def test_para_teacher_can_get_own_session_plan_week():
    token = login(
        PARA_TEACHERS["PT001"]["email"]
    )

    created = create_week(token)

    response = client.get(
        "/api/v1/session-plans/weeks/2026-09-21",
        headers=auth_headers(token),
    )

    assert response.status_code == 200, response.text

    data = response.json()

    assert data["week"]["id"] == created["id"]
    assert data["week"]["week_start_date"] == "2026-09-21"
    assert data["week"]["week_end_date"] == "2026-09-27"
    assert data["items"] == []


def test_para_teacher_cannot_get_another_teachers_week():
    """
    Planning ownership is tied to the authenticated para-teacher.
    """

    pt001_token = login(
        PARA_TEACHERS["PT001"]["email"]
    )

    pt002_token = login(
        PARA_TEACHERS["PT002"]["email"]
    )

    create_week(
        pt002_token,
        "2026-09-21",
    )

    response = client.get(
        "/api/v1/session-plans/weeks/2026-09-21",
        headers=auth_headers(pt001_token),
    )

    assert response.status_code == 404


def test_get_nonexistent_session_plan_week_returns_not_found():
    token = login(
        PARA_TEACHERS["PT001"]["email"]
    )

    response = client.get(
        "/api/v1/session-plans/weeks/2026-10-05",
        headers=auth_headers(token),
    )

    assert response.status_code == 404


# ----------------------------------------------------------------------
# ITEM CREATION
# ----------------------------------------------------------------------


def test_session_plan_item_creation_requires_authentication():
    response = client.post(
        "/api/v1/session-plans/items",
        json={
            "session_plan_week_id": (
                "00000000-0000-0000-0000-000000000001"
            ),
            "class_division_id": (
                "00000000-0000-0000-0000-000000000002"
            ),
            "planned_date": "2026-09-21",
            "sequence_no": 1,
        },
    )

    assert response.status_code == 401


def test_para_teacher_can_create_session_plan_item():
    token = login(
        PARA_TEACHERS["PT001"]["email"]
    )

    week = create_week(token)

    division = get_first_class_division(token)

    response = client.post(
        "/api/v1/session-plans/items",
        headers=auth_headers(token),
        json={
            "session_plan_week_id": week["id"],
            "class_division_id": division["id"],
            "planned_date": "2026-09-21",
            "sequence_no": 1,
        },
    )

    assert response.status_code == 201, response.text

    data = response.json()

    assert data["session_plan_week_id"] == week["id"]
    assert data["class_division_id"] == division["id"]
    assert data["planned_date"] == "2026-09-21"
    assert data["sequence_no"] == 1
    assert data["planned_start_time"] is None
    assert data["planned_end_time"] is None
    assert data["data_origin"] == "PRODUCTION"


def test_session_plan_item_accepts_valid_planned_times():
    token = login(
        PARA_TEACHERS["PT001"]["email"]
    )

    week = create_week(token)

    division = get_first_class_division(token)

    item = create_item(
        token,
        week["id"],
        division["id"],
        planned_start_time="09:00:00",
        planned_end_time="10:00:00",
    )

    assert item["planned_start_time"] == "09:00:00"
    assert item["planned_end_time"] == "10:00:00"


@pytest.mark.parametrize(
    "time_payload",
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
def test_invalid_session_plan_item_time_range_is_rejected(
    time_payload,
):
    token = login(
        PARA_TEACHERS["PT001"]["email"]
    )

    week = create_week(token)

    division = get_first_class_division(token)

    response = client.post(
        "/api/v1/session-plans/items",
        headers=auth_headers(token),
        json={
            "session_plan_week_id": week["id"],
            "class_division_id": division["id"],
            "planned_date": "2026-09-21",
            "sequence_no": 1,
            **time_payload,
        },
    )

    assert response.status_code == 422


def test_sequence_number_must_be_positive():
    token = login(
        PARA_TEACHERS["PT001"]["email"]
    )

    week = create_week(token)

    division = get_first_class_division(token)

    response = client.post(
        "/api/v1/session-plans/items",
        headers=auth_headers(token),
        json={
            "session_plan_week_id": week["id"],
            "class_division_id": division["id"],
            "planned_date": "2026-09-21",
            "sequence_no": 0,
        },
    )

    assert response.status_code == 422


def test_negative_sequence_number_is_rejected():
    token = login(
        PARA_TEACHERS["PT001"]["email"]
    )

    week = create_week(token)

    division = get_first_class_division(token)

    response = client.post(
        "/api/v1/session-plans/items",
        headers=auth_headers(token),
        json={
            "session_plan_week_id": week["id"],
            "class_division_id": division["id"],
            "planned_date": "2026-09-21",
            "sequence_no": -1,
        },
    )

    assert response.status_code == 422


def test_nonexistent_class_division_returns_not_found():
    token = login(
        PARA_TEACHERS["PT001"]["email"]
    )

    week = create_week(token)

    response = client.post(
        "/api/v1/session-plans/items",
        headers=auth_headers(token),
        json={
            "session_plan_week_id": week["id"],
            "class_division_id": (
                "00000000-0000-0000-0000-000000000000"
            ),
            "planned_date": "2026-09-21",
            "sequence_no": 1,
        },
    )

    assert response.status_code == 404

    assert response.json()["detail"] == (
        "Class division not found."
    )


def test_para_teacher_cannot_create_item_for_another_school():
    pt001_token = login(
        PARA_TEACHERS["PT001"]["email"]
    )

    pt002_token = login(
        PARA_TEACHERS["PT002"]["email"]
    )

    pt001_week = create_week(pt001_token)

    pt002_division = get_first_class_division(
        pt002_token
    )

    response = client.post(
        "/api/v1/session-plans/items",
        headers=auth_headers(pt001_token),
        json={
            "session_plan_week_id": pt001_week["id"],
            "class_division_id": pt002_division["id"],
            "planned_date": "2026-09-21",
            "sequence_no": 1,
        },
    )

    assert response.status_code == 403

    assert response.json()["detail"] == (
        "You are not authorized to access this school."
    )


def test_client_cannot_control_item_data_origin():
    token = login(
        PARA_TEACHERS["PT001"]["email"]
    )

    week = create_week(token)

    division = get_first_class_division(token)

    response = client.post(
        "/api/v1/session-plans/items",
        headers=auth_headers(token),
        json={
            "session_plan_week_id": week["id"],
            "class_division_id": division["id"],
            "planned_date": "2026-09-21",
            "sequence_no": 1,
            "data_origin": "DEMO",
        },
    )

    assert response.status_code == 201, response.text

    assert response.json()["data_origin"] == "PRODUCTION"


def test_item_date_must_belong_to_planning_week():
    token = login(
        PARA_TEACHERS["PT001"]["email"]
    )

    week = create_week(token)

    division = get_first_class_division(token)

    response = client.post(
        "/api/v1/session-plans/items",
        headers=auth_headers(token),
        json={
            "session_plan_week_id": week["id"],
            "class_division_id": division["id"],
            "planned_date": "2026-09-28",
            "sequence_no": 1,
        },
    )

    assert response.status_code == 400


def test_duplicate_sequence_number_is_rejected():
    token = login(
        PARA_TEACHERS["PT001"]["email"]
    )

    week = create_week(token)

    division = get_first_class_division(token)

    first = create_item(
        token,
        week["id"],
        division["id"],
        sequence_no=1,
    )

    assert first["sequence_no"] == 1

    response = client.post(
        "/api/v1/session-plans/items",
        headers=auth_headers(token),
        json={
            "session_plan_week_id": week["id"],
            "class_division_id": division["id"],
            "planned_date": "2026-09-22",
            "sequence_no": 1,
        },
    )

    assert response.status_code == 409


# ----------------------------------------------------------------------
# WEEK DETAIL / ORDERING
# ----------------------------------------------------------------------


def test_week_detail_returns_items_ordered_by_date_and_sequence():
    token = login(
        PARA_TEACHERS["PT001"]["email"]
    )

    week = create_week(token)

    division = get_first_class_division(token)

    create_item(
        token,
        week["id"],
        division["id"],
        planned_date="2026-09-23",
        sequence_no=3,
    )

    create_item(
        token,
        week["id"],
        division["id"],
        planned_date="2026-09-22",
        sequence_no=2,
    )

    # Use another division for the same week/date when available.
    db = SessionLocal()

    try:
        divisions = (
            db.query(ClassDivision)
            .filter(
                ClassDivision.school_id
                == (
                    db.query(ClassDivision.school_id)
                    .filter(ClassDivision.id == division["id"])
                    .scalar_subquery()
                )
            )
            .order_by(ClassDivision.id)
            .all()
        )
    finally:
        db.close()

    if len(divisions) < 2:
        pytest.skip(
            "Demo school must contain at least two class divisions "
            "for same-date sequence ordering test."
        )

    second_division = next(
        (
            d
            for d in divisions
            if str(d.id) != division["id"]
        ),
        None,
    )

    if second_division is None:
        pytest.skip(
            "No second class division available."
        )

    create_item(
        token,
        week["id"],
        str(second_division.id),
        planned_date="2026-09-21",
        sequence_no=1,
    )

    response = client.get(
        "/api/v1/session-plans/weeks/2026-09-21",
        headers=auth_headers(token),
    )

    assert response.status_code == 200, response.text

    items = response.json()["items"]

    assert [
        (item["planned_date"], item["sequence_no"])
        for item in items
    ] == [
        ("2026-09-21", 1),
        ("2026-09-22", 2),
        ("2026-09-23", 3),
    ]


# ----------------------------------------------------------------------
# ITEM UPDATE
# ----------------------------------------------------------------------


def test_item_update_requires_authentication():
    response = client.patch(
        "/api/v1/session-plans/items/"
        "00000000-0000-0000-0000-000000000000",
        json={
            "planned_date": "2026-09-22",
        },
    )

    assert response.status_code == 401


def test_para_teacher_can_update_editable_item():
    token = login(
        PARA_TEACHERS["PT001"]["email"]
    )

    week = create_week(token)

    division = get_first_class_division(token)

    item = create_item(
        token,
        week["id"],
        division["id"],
        planned_date="2026-09-21",
        sequence_no=1,
    )

    response = client.patch(
        f"/api/v1/session-plans/items/{item['id']}",
        headers=auth_headers(token),
        json={
            "planned_date": "2026-09-22",
            "planned_start_time": "09:00:00",
            "planned_end_time": "10:00:00",
        },
    )

    assert response.status_code == 200, response.text

    data = response.json()

    assert data["id"] == item["id"]
    assert data["planned_date"] == "2026-09-22"
    assert data["planned_start_time"] == "09:00:00"
    assert data["planned_end_time"] == "10:00:00"


def test_update_nonexistent_item_returns_not_found():
    token = login(
        PARA_TEACHERS["PT001"]["email"]
    )

    response = client.patch(
        "/api/v1/session-plans/items/"
        "00000000-0000-0000-0000-000000000000",
        headers=auth_headers(token),
        json={
            "planned_date": "2026-09-22",
        },
    )

    assert response.status_code == 404


def test_para_teacher_cannot_update_item_from_another_school():
    pt001_token = login(
        PARA_TEACHERS["PT001"]["email"]
    )

    pt002_token = login(
        PARA_TEACHERS["PT002"]["email"]
    )

    pt002_week = create_week(
        pt002_token,
        "2026-09-21",
    )

    pt002_division = get_first_class_division(
        pt002_token
    )

    item = create_item(
        pt002_token,
        pt002_week["id"],
        pt002_division["id"],
    )

    response = client.patch(
        f"/api/v1/session-plans/items/{item['id']}",
        headers=auth_headers(pt001_token),
        json={
            "planned_date": "2026-09-22",
        },
    )

    assert response.status_code == 403

    assert response.json()["detail"] == (
        "You are not authorized to access this school."
    )


# ----------------------------------------------------------------------
# ITEM DELETE
# ----------------------------------------------------------------------


def test_item_delete_requires_authentication():
    response = client.delete(
        "/api/v1/session-plans/items/"
        "00000000-0000-0000-0000-000000000000",
    )

    assert response.status_code == 401


def test_para_teacher_can_delete_editable_item():
    token = login(
        PARA_TEACHERS["PT001"]["email"]
    )

    week = create_week(token)

    division = get_first_class_division(token)

    item = create_item(
        token,
        week["id"],
        division["id"],
        sequence_no=1,
    )

    response = client.delete(
        f"/api/v1/session-plans/items/{item['id']}",
        headers=auth_headers(token),
    )

    assert response.status_code == 204

    get_response = client.get(
        "/api/v1/session-plans/weeks/2026-09-21",
        headers=auth_headers(token),
    )

    assert get_response.status_code == 200

    assert all(
        existing["id"] != item["id"]
        for existing in get_response.json()["items"]
    )


def test_delete_nonexistent_item_returns_not_found():
    token = login(
        PARA_TEACHERS["PT001"]["email"]
    )

    response = client.delete(
        "/api/v1/session-plans/items/"
        "00000000-0000-0000-0000-000000000000",
        headers=auth_headers(token),
    )

    assert response.status_code == 404


# ----------------------------------------------------------------------
# LESSON PLAN CONTENT
# ----------------------------------------------------------------------


def test_get_content_requires_authentication():
    response = client.get(
        "/api/v1/session-plans/items/"
        "00000000-0000-0000-0000-000000000000/content",
    )

    assert response.status_code == 401


def test_put_content_requires_authentication():
    response = client.put(
        "/api/v1/session-plans/items/"
        "00000000-0000-0000-0000-000000000000/content",
        json={
            "content": "Lesson plan",
        },
    )

    assert response.status_code == 401


def test_para_teacher_can_create_lesson_plan_content():
    token = login(
        PARA_TEACHERS["PT001"]["email"]
    )

    week = create_week(token)

    division = get_first_class_division(token)

    item = create_item(
        token,
        week["id"],
        division["id"],
    )

    response = client.put(
        f"/api/v1/session-plans/items/{item['id']}/content",
        headers=auth_headers(token),
        json={
            "content": "Introduction to fractions.",
        },
    )

    assert response.status_code == 200, response.text

    data = response.json()

    assert data["session_plan_item_id"] == item["id"]
    assert data["content"] == "Introduction to fractions."
    assert data["data_origin"] == "PRODUCTION"


def test_lesson_plan_content_can_be_retrieved():
    token = login(
        PARA_TEACHERS["PT001"]["email"]
    )

    week = create_week(token)

    division = get_first_class_division(token)

    item = create_item(
        token,
        week["id"],
        division["id"],
    )

    create_response = client.put(
        f"/api/v1/session-plans/items/{item['id']}/content",
        headers=auth_headers(token),
        json={
            "content": "Fractions lesson.",
        },
    )

    assert create_response.status_code == 200

    response = client.get(
        f"/api/v1/session-plans/items/{item['id']}/content",
        headers=auth_headers(token),
    )

    assert response.status_code == 200

    data = response.json()

    assert data["session_plan_item_id"] == item["id"]
    assert data["content"] == "Fractions lesson."


def test_lesson_plan_content_is_upserted():
    token = login(
        PARA_TEACHERS["PT001"]["email"]
    )

    week = create_week(token)

    division = get_first_class_division(token)

    item = create_item(
        token,
        week["id"],
        division["id"],
    )

    first_response = client.put(
        f"/api/v1/session-plans/items/{item['id']}/content",
        headers=auth_headers(token),
        json={
            "content": "Original lesson.",
        },
    )

    assert first_response.status_code == 200

    first_id = first_response.json()["id"]

    second_response = client.put(
        f"/api/v1/session-plans/items/{item['id']}/content",
        headers=auth_headers(token),
        json={
            "content": "Updated lesson.",
        },
    )

    assert second_response.status_code == 200

    data = second_response.json()

    assert data["id"] == first_id
    assert data["session_plan_item_id"] == item["id"]
    assert data["content"] == "Updated lesson."


@pytest.mark.parametrize(
    "content",
    [
        "",
        " ",
    ],
)
def test_empty_lesson_plan_content_is_rejected(content):
    token = login(
        PARA_TEACHERS["PT001"]["email"]
    )

    week = create_week(token)

    division = get_first_class_division(token)

    item = create_item(
        token,
        week["id"],
        division["id"],
    )

    response = client.put(
        f"/api/v1/session-plans/items/{item['id']}/content",
        headers=auth_headers(token),
        json={
            "content": content,
        },
    )

    assert response.status_code == 422


def test_client_cannot_control_content_data_origin():
    token = login(
        PARA_TEACHERS["PT001"]["email"]
    )

    week = create_week(token)

    division = get_first_class_division(token)

    item = create_item(
        token,
        week["id"],
        division["id"],
    )

    response = client.put(
        f"/api/v1/session-plans/items/{item['id']}/content",
        headers=auth_headers(token),
        json={
            "content": "Lesson content.",
            "data_origin": "DEMO",
        },
    )

    assert response.status_code == 200

    assert response.json()["data_origin"] == "PRODUCTION"


def test_get_missing_content_returns_not_found():
    token = login(
        PARA_TEACHERS["PT001"]["email"]
    )

    week = create_week(token)

    division = get_first_class_division(token)

    item = create_item(
        token,
        week["id"],
        division["id"],
    )

    response = client.get(
        f"/api/v1/session-plans/items/{item['id']}/content",
        headers=auth_headers(token),
    )

    assert response.status_code == 404


def test_para_teacher_cannot_access_content_from_another_school():
    pt001_token = login(
        PARA_TEACHERS["PT001"]["email"]
    )

    pt002_token = login(
        PARA_TEACHERS["PT002"]["email"]
    )

    week = create_week(pt002_token)

    division = get_first_class_division(pt002_token)

    item = create_item(
        pt002_token,
        week["id"],
        division["id"],
    )

    client.put(
        f"/api/v1/session-plans/items/{item['id']}/content",
        headers=auth_headers(pt002_token),
        json={
            "content": "Private lesson plan.",
        },
    )

    response = client.get(
        f"/api/v1/session-plans/items/{item['id']}/content",
        headers=auth_headers(pt001_token),
    )

    assert response.status_code == 403

    assert response.json()["detail"] == (
        "You are not authorized to access this school."
    )


# ----------------------------------------------------------------------
# VALIDATION / TEACHING READINESS
# ----------------------------------------------------------------------


def test_validate_item_requires_authentication():
    response = client.post(
        "/api/v1/session-plans/items/"
        "00000000-0000-0000-0000-000000000000/validate",
    )

    assert response.status_code == 401


def test_validate_nonexistent_item_returns_not_found():
    token = login(
        PARA_TEACHERS["PT001"]["email"]
    )

    response = client.post(
        "/api/v1/session-plans/items/"
        "00000000-0000-0000-0000-000000000000/validate",
        headers=auth_headers(token),
    )

    assert response.status_code == 404


def test_validate_item_without_content_returns_conflict():
    token = login(
        PARA_TEACHERS["PT001"]["email"]
    )

    week = create_week(token)

    division = get_first_class_division(token)

    item = create_item(
        token,
        week["id"],
        division["id"],
    )

    response = client.post(
        f"/api/v1/session-plans/items/{item['id']}/validate",
        headers=auth_headers(token),
    )

    assert response.status_code == 409


def test_validate_item_with_content_succeeds():
    token = login(
        PARA_TEACHERS["PT001"]["email"]
    )

    week = create_week(token)

    division = get_first_class_division(token)

    item = create_item(
        token,
        week["id"],
        division["id"],
        planned_date="2026-09-21",
        sequence_no=1,
    )

    create_item(
        token,
        week["id"],
        division["id"],
        planned_date="2026-09-22",
        sequence_no=2,
    )

    create_item(
        token,
        week["id"],
        division["id"],
        planned_date="2026-09-23",
        sequence_no=3,
    )

    create_item(
        token,
        week["id"],
        division["id"],
        planned_date="2026-09-24",
        sequence_no=4,
    )

    create_item(
        token,
        week["id"],
        division["id"],
        planned_date="2026-09-25",
        sequence_no=5,
    )

    create_item(
        token,
        week["id"],
        division["id"],
        planned_date="2026-09-26",
        sequence_no=6,
    )

    content_response = client.put(
        f"/api/v1/session-plans/items/{item['id']}/content",
        headers=auth_headers(token),
        json={
            "content": "Complete lesson plan.",
        },
    )

    assert content_response.status_code == 200

    response = client.post(
        f"/api/v1/session-plans/items/{item['id']}/validate",
        headers=auth_headers(token),
    )

    assert response.status_code == 200, response.text

    data = response.json()

    assert data["id"] == item["id"]
    assert data["session_plan_week_id"] == week["id"]
    assert data["class_division_id"] == division["id"]


def test_para_teacher_cannot_validate_item_from_another_school():
    pt001_token = login(
        PARA_TEACHERS["PT001"]["email"]
    )

    pt002_token = login(
        PARA_TEACHERS["PT002"]["email"]
    )

    week = create_week(pt002_token)

    division = get_first_class_division(pt002_token)

    item = create_item(
        pt002_token,
        week["id"],
        division["id"],
    )

    response = client.post(
        f"/api/v1/session-plans/items/{item['id']}/validate",
        headers=auth_headers(pt001_token),
    )

    assert response.status_code == 403

    assert response.json()["detail"] == (
        "You are not authorized to access this school."
    )