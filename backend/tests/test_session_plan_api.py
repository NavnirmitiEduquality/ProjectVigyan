from datetime import date, time, timedelta
import os
from uuid import UUID
import uuid
import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models import (
    ClassDivision,
    Role,
    School,
    SessionPlanAttachment,
    SessionPlanContent,
    SessionPlanItem,
    SessionPlanWeek,
    TeachingSession,
    User,
    UserAssignment,
    UserRole,
)
from app.services.auth_service import hash_password
from app.services.session_plan.service import SessionPlanService


load_dotenv()

DEMO_PASSWORD = os.getenv("DEMO_USER_PASSWORD")

if not DEMO_PASSWORD:
    raise RuntimeError(
        "DEMO_USER_PASSWORD must be configured in .env "
        "before running session-plan API tests."
    )


client = TestClient(app)


PT001_EMAIL = None
PT002_EMAIL = None

@pytest.fixture(scope="module", autouse=True)
def session_plan_api_test_environment():
    """
    Provision two isolated TEST Para-Teacher accounts,
    each with a separate TEST school and three divisions.
    """
    global PT001_EMAIL, PT002_EMAIL

    db = SessionLocal()
    suffix = uuid.uuid4().hex[:12]

    school_ids = []
    teacher_ids = []

    teacher_configs = {
        "PT001": {
            "email": f"pt001-{suffix}@test.vigyan.com",
            "school_code": f"AP1-{suffix}",
        },
        "PT002": {
            "email": f"pt002-{suffix}@test.vigyan.com",
            "school_code": f"AP2-{suffix}",
        },
    }

    try:
        teacher_role = (
            db.query(Role)
            .filter(Role.code == "PARA_TEACHER")
            .first()
        )

        assert teacher_role is not None, (
            "PARA_TEACHER role must be seeded."
        )

        for code, config in teacher_configs.items():
            school = School(
                school_code=config["school_code"],
                school_name=f"Session Plan API {code} Test School",
                status="ACTIVE",
                data_origin="TEST",
            )
            db.add(school)
            db.flush()

            school_ids.append(school.id)

            for division_name in ["A", "B", "C"]:
                db.add(
                    ClassDivision(
                        school_id=school.id,
                        class_level=5,
                        division=division_name,
                        status="ACTIVE",
                        data_origin="TEST",
                    )
                )

            teacher = User(
                user_code=f"API-{code}-{suffix}",
                account_category="PARA_TEACHER",
                full_name=f"Session Plan API Test {code}",
                email=config["email"],
                password_hash=hash_password(DEMO_PASSWORD),
                status="ACTIVE",
                data_origin="TEST",
            )

            db.add(teacher)
            db.flush()

            teacher_ids.append(teacher.id)

            db.add_all([
                UserRole(
                    user_id=teacher.id,
                    role_id=teacher_role.id,
                    is_active=True,
                ),
                UserAssignment(
                    user_id=teacher.id,
                    scope_type="SCHOOL",
                    school_id=school.id,
                    start_date=date(2026, 1, 1),
                    end_date=None,
                    is_active=True,
                ),
            ])

        db.commit()

        PT001_EMAIL = teacher_configs["PT001"]["email"]
        PT002_EMAIL = teacher_configs["PT002"]["email"]

        print(
            "\nCreated isolated TEST session-plan API environment "
            f"({suffix})."
        )

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()

    yield

    # Remove linked TeachingSessions and planning data first.
    _cleanup_session_plan_api_state(teacher_ids)

    cleanup_db = SessionLocal()

    try:
        cleanup_db.query(UserAssignment).filter(
            UserAssignment.user_id.in_(teacher_ids)
        ).delete(synchronize_session=False)

        cleanup_db.query(UserRole).filter(
            UserRole.user_id.in_(teacher_ids)
        ).delete(synchronize_session=False)

        cleanup_db.query(ClassDivision).filter(
            ClassDivision.school_id.in_(school_ids)
        ).delete(synchronize_session=False)

        cleanup_db.query(User).filter(
            User.id.in_(teacher_ids)
        ).delete(synchronize_session=False)

        cleanup_db.query(School).filter(
            School.id.in_(school_ids)
        ).delete(synchronize_session=False)

        cleanup_db.commit()

        print(
            "\nRemoved isolated TEST session-plan API environment."
        )

    except Exception:
        cleanup_db.rollback()
        raise

    finally:
        cleanup_db.close()


def _cleanup_session_plan_api_state(teacher_ids):
    db = SessionLocal()

    try:
        weeks = (
            db.query(SessionPlanWeek)
            .filter(
                SessionPlanWeek.para_teacher_id.in_(teacher_ids)
            )
            .all()
        )

        week_ids = [week.id for week in weeks]

        if not week_ids:
            return

        items = (
            db.query(SessionPlanItem)
            .filter(
                SessionPlanItem.session_plan_week_id.in_(week_ids)
            )
            .all()
        )

        item_ids = [item.id for item in items]

        if item_ids:
            # TeachingSession has a link to SessionPlanItem.
            db.query(TeachingSession).filter(
                TeachingSession.session_plan_item_id.in_(item_ids)
            ).delete(synchronize_session=False)

            contents = (
                db.query(SessionPlanContent)
                .filter(
                    SessionPlanContent.session_plan_item_id.in_(
                        item_ids
                    )
                )
                .all()
            )

            content_ids = [content.id for content in contents]

            if content_ids:
                db.query(SessionPlanAttachment).filter(
                    SessionPlanAttachment.session_plan_content_id.in_(
                        content_ids
                    )
                ).delete(synchronize_session=False)

                db.query(SessionPlanContent).filter(
                    SessionPlanContent.id.in_(content_ids)
                ).delete(synchronize_session=False)

            db.query(SessionPlanItem).filter(
                SessionPlanItem.id.in_(item_ids)
            ).delete(synchronize_session=False)

        db.query(SessionPlanWeek).filter(
            SessionPlanWeek.id.in_(week_ids)
        ).delete(synchronize_session=False)

        db.commit()

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


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


def get_user_id_by_email(email: str) -> UUID:
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


def get_first_class_division(token: str) -> dict:
    response = client.get(
        "/api/v1/class-divisions",
        headers=auth_headers(token),
    )

    assert response.status_code == 200, response.text

    divisions = response.json()

    assert divisions

    return divisions[0]


def get_test_class_divisions_for_school(
    db,
    school_id: UUID,
    count: int = 3,
) -> list[ClassDivision]:
    divisions = (
        db.query(ClassDivision)
        .filter(
            ClassDivision.school_id == school_id,
            ClassDivision.data_origin == "TEST",
        )
        .order_by(ClassDivision.id)
        .limit(count)
        .all()
    )

    if len(divisions) < count:
        pytest.skip(
            f"Need at least {count} TEST class divisions "
            f"in school {school_id}."
        )

    return divisions


def get_unique_week_start(
    db,
    para_teacher_id: UUID,
) -> date:
    """
    Find a Monday not already used by this teacher.

    The API tests create committed production TeachingSessions,
    so using an unused planning week keeps repeated test runs
    independent of previously-created rows.
    """

    candidate = date(2026, 10, 5)

    while (
        db.query(
            SessionPlanItem.session_plan_week_id
        )
        .join(
            SessionPlanWeek,
            SessionPlanItem.session_plan_week_id
            == SessionPlanWeek.id,
        )
        .filter(
            SessionPlanWeek.para_teacher_id == para_teacher_id,
            SessionPlanWeek.week_start_date == candidate,
        )
        .first()
        is not None
    ):
        candidate += timedelta(days=7)

    return candidate


def create_plan_items(
    *,
    para_teacher_id: UUID,
    school_id: UUID,
    item_count: int = 6,
    add_content: bool = True,
) -> tuple[UUID, list[UUID]]:
    """
    Seed a valid or intentionally-invalid planning week directly
    through the service layer.

    The HTTP request under test is still the TeachingSession
    linkage endpoint.

    IMPORTANT:
    This helper returns item IDs rather than ORM instances.
    The SessionLocal session is closed before returning, so
    returning ORM objects would make their attributes unsafe
    to access later.
    """

    db = SessionLocal()

    try:
        divisions = get_test_class_divisions_for_school(
            db,
            school_id,
            count=3,
        )

        service = SessionPlanService()

        week_start = get_unique_week_start(
            db,
            para_teacher_id,
        )

        week = service.get_or_create_week(
            db,
            para_teacher_id=para_teacher_id,
            week_start_date=week_start,
            data_origin="TEST",
        )

        items = []

        for index in range(item_count):
            division = divisions[index % len(divisions)]

            item = service.create_item(
                db,
                para_teacher_id=para_teacher_id,
                session_plan_week_id=week.id,
                class_division_id=division.id,
                planned_date=week_start + timedelta(days=index),
                sequence_no=index + 1,
                planned_start_time=time(9, 0),
                planned_end_time=time(9, 45),
                data_origin="TEST",
            )

            items.append(item)

        if add_content and items:
            service.set_content(
                db,
                para_teacher_id=para_teacher_id,
                item_id=items[0].id,
                content="API integration test lesson plan.",
                data_origin="TEST",
            )

        item_ids = [item.id for item in items]

        db.commit()

        return week.id, item_ids

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


def get_session_plan_item(item_id: UUID) -> SessionPlanItem:
    """
    Reload a SessionPlanItem using a fresh database session.

    This avoids DetachedInstanceError after create_plan_items()
    closes its SessionLocal session.
    """

    db = SessionLocal()

    try:
        item = (
            db.query(SessionPlanItem)
            .filter(SessionPlanItem.id == item_id)
            .first()
        )

        assert item is not None, (
            f"SessionPlanItem not found: {item_id}"
        )

        return {
            "id": item.id,
            "class_division_id": item.class_division_id,
            "planned_date": item.planned_date,
            "planned_start_time": item.planned_start_time,
            "planned_end_time": item.planned_end_time,
        }

    finally:
        db.close()


# ----------------------------------------------------------------------
# AUTHENTICATION
# ----------------------------------------------------------------------


def test_create_teaching_session_from_plan_requires_authentication():
    response = client.post(
        "/api/v1/session-plans/items/"
        "00000000-0000-0000-0000-000000000000/"
        "teaching-session",
    )

    assert response.status_code == 401


# ----------------------------------------------------------------------
# NOT FOUND
# ----------------------------------------------------------------------


def test_create_teaching_session_from_nonexistent_plan_item_returns_not_found():
    token = login(PT001_EMAIL)

    response = client.post(
        "/api/v1/session-plans/items/"
        "00000000-0000-0000-0000-000000000000/"
        "teaching-session",
        headers=auth_headers(token),
    )

    assert response.status_code == 404


# ----------------------------------------------------------------------
# HAPPY PATH
# ----------------------------------------------------------------------


def test_create_teaching_session_from_valid_plan_item():
    token = login(PT001_EMAIL)

    user_id = get_user_id_by_email(PT001_EMAIL)

    class_division = get_first_class_division(token)

    _, item_ids = create_plan_items(
        para_teacher_id=user_id,
        school_id=UUID(class_division["school_id"]),
        item_count=6,
        add_content=True,
    )

    item_id = item_ids[0]

    item = get_session_plan_item(item_id)

    response = client.post(
        f"/api/v1/session-plans/items/{item_id}/teaching-session",
        headers=auth_headers(token),
    )

    assert response.status_code == 201, response.text

    data = response.json()

    assert data["id"]
    assert data["session_plan_item_id"] == str(item_id)
    assert data["class_division_id"] == str(
        item["class_division_id"]
    )
    assert data["para_teacher_id"] == str(user_id)
    assert data["session_date"] == str(
        item["planned_date"]
    )
    assert data["planned_start_time"] == "09:00:00"
    assert data["planned_end_time"] == "09:45:00"
    assert data["status"] == "PLANNED"
    assert data["data_origin"] == "PRODUCTION"


def test_create_teaching_session_from_plan_persists_exactly_one_link():
    token = login(PT001_EMAIL)

    user_id = get_user_id_by_email(PT001_EMAIL)
    class_division = get_first_class_division(token)

    _, item_ids = create_plan_items(
        para_teacher_id=user_id,
        school_id=UUID(class_division["school_id"]),
        item_count=6,
        add_content=True,
    )

    item_id = item_ids[0]

    first_response = client.post(
        f"/api/v1/session-plans/items/{item_id}/teaching-session",
        headers=auth_headers(token),
    )

    assert first_response.status_code == 201, first_response.text

    session_id = UUID(first_response.json()["id"])

    db = SessionLocal()

    try:
        sessions = (
            db.query(TeachingSession)
            .filter(
                TeachingSession.session_plan_item_id == item_id,
            )
            .all()
        )

        assert len(sessions) == 1
        assert sessions[0].id == session_id
        assert sessions[0].session_plan_item_id == item_id
        assert sessions[0].status == "PLANNED"
        assert sessions[0].data_origin == "PRODUCTION"

    finally:
        db.close()


# ----------------------------------------------------------------------
# DUPLICATE LINK
# ----------------------------------------------------------------------


def test_duplicate_session_plan_link_returns_conflict():
    token = login(PT001_EMAIL)

    user_id = get_user_id_by_email(PT001_EMAIL)
    class_division = get_first_class_division(token)

    _, item_ids = create_plan_items(
        para_teacher_id=user_id,
        school_id=UUID(class_division["school_id"]),
        item_count=6,
        add_content=True,
    )

    item_id = item_ids[0]

    first_response = client.post(
        f"/api/v1/session-plans/items/{item_id}/teaching-session",
        headers=auth_headers(token),
    )

    assert first_response.status_code == 201, first_response.text

    first_session_id = first_response.json()["id"]

    second_response = client.post(
        f"/api/v1/session-plans/items/{item_id}/teaching-session",
        headers=auth_headers(token),
    )

    assert second_response.status_code == 409
    assert (
        "already linked"
        in second_response.json()["detail"].lower()
    )

    db = SessionLocal()

    try:
        sessions = (
            db.query(TeachingSession)
            .filter(
                TeachingSession.session_plan_item_id == item_id,
            )
            .all()
        )

        assert len(sessions) == 1
        assert str(sessions[0].id) == first_session_id

    finally:
        db.close()


# ----------------------------------------------------------------------
# LESSON PLAN CONTENT
# ----------------------------------------------------------------------


def test_teaching_session_link_requires_lesson_plan_content():
    token = login(PT001_EMAIL)

    user_id = get_user_id_by_email(PT001_EMAIL)
    class_division = get_first_class_division(token)

    _, item_ids = create_plan_items(
        para_teacher_id=user_id,
        school_id=UUID(class_division["school_id"]),
        item_count=6,
        add_content=False,
    )

    item_id = item_ids[0]

    response = client.post(
        f"/api/v1/session-plans/items/{item_id}/teaching-session",
        headers=auth_headers(token),
    )

    assert response.status_code == 409
    assert (
        "lesson-plan content"
        in response.json()["detail"].lower()
    )

    db = SessionLocal()

    try:
        assert (
            db.query(TeachingSession)
            .filter(
                TeachingSession.session_plan_item_id == item_id,
            )
            .count()
            == 0
        )

    finally:
        db.close()


# ----------------------------------------------------------------------
# WEEK VALIDATION
# ----------------------------------------------------------------------


def test_teaching_session_link_requires_six_weekly_items():
    token = login(PT001_EMAIL)

    user_id = get_user_id_by_email(PT001_EMAIL)
    class_division = get_first_class_division(token)

    _, item_ids = create_plan_items(
        para_teacher_id=user_id,
        school_id=UUID(class_division["school_id"]),
        item_count=5,
        add_content=True,
    )

    item_id = item_ids[0]

    response = client.post(
        f"/api/v1/session-plans/items/{item_id}/teaching-session",
        headers=auth_headers(token),
    )

    assert response.status_code == 409
    assert "6" in response.json()["detail"]


# ----------------------------------------------------------------------
# SCHOOL AUTHORIZATION
# ----------------------------------------------------------------------


def test_para_teacher_cannot_link_plan_item_from_another_school():
    pt001_token = login(PT001_EMAIL)
    pt002_token = login(PT002_EMAIL)

    pt002_user_id = get_user_id_by_email(PT002_EMAIL)

    pt002_division = get_first_class_division(pt002_token)

    _, item_ids = create_plan_items(
        para_teacher_id=pt002_user_id,
        school_id=UUID(pt002_division["school_id"]),
        item_count=6,
        add_content=True,
    )

    item_id = item_ids[0]

    response = client.post(
        f"/api/v1/session-plans/items/{item_id}/teaching-session",
        headers=auth_headers(pt001_token),
    )

    assert response.status_code == 403
    assert response.json()["detail"] == (
        "You are not authorized to access this school."
    )

    db = SessionLocal()

    try:
        assert (
            db.query(TeachingSession)
            .filter(
                TeachingSession.session_plan_item_id == item_id,
            )
            .count()
            == 0
        )

    finally:
        db.close()


# ----------------------------------------------------------------------
# SERVER-CONTROLLED VALUES
# ----------------------------------------------------------------------


def test_plan_link_does_not_accept_client_supplied_session_values():
    token = login(PT001_EMAIL)

    user_id = get_user_id_by_email(PT001_EMAIL)
    class_division = get_first_class_division(token)

    _, item_ids = create_plan_items(
        para_teacher_id=user_id,
        school_id=UUID(class_division["school_id"]),
        item_count=6,
        add_content=True,
    )

    item_id = item_ids[0]

    item = get_session_plan_item(item_id)

    # The endpoint has no request body. Supplying these values must
    # not alter the values inherited from the SessionPlanItem.
    response = client.post(
        f"/api/v1/session-plans/items/{item_id}/teaching-session",
        headers=auth_headers(token),
        json={
            "class_division_id": (
                "00000000-0000-0000-0000-000000000001"
            ),
            "para_teacher_id": (
                "00000000-0000-0000-0000-000000000002"
            ),
            "session_date": "2099-01-01",
            "planned_start_time": "22:00:00",
            "planned_end_time": "23:00:00",
        },
    )

    assert response.status_code == 201, response.text

    data = response.json()

    assert data["session_plan_item_id"] == str(item_id)
    assert data["class_division_id"] == str(
        item["class_division_id"]
    )
    assert data["para_teacher_id"] == str(user_id)
    assert data["session_date"] == str(
        item["planned_date"]
    )
    assert data["planned_start_time"] == "09:00:00"
    assert data["planned_end_time"] == "09:45:00"