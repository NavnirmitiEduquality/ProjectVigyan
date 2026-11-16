from datetime import date
import os
import uuid
from pathlib import Path
from sqlalchemy import select

import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models import (
    ClassDivision,
    Role,
    School,
    SessionPlanContent,
    SessionPlanItem,
    SessionPlanWeek,
    SessionPlanAttachment,
    User,
    UserAssignment,
    UserRole,
)
from app.routers import session_plan as session_plan_router
from app.services.session_plan.attachment_storage import (
    SessionPlanAttachmentStorage,
)
from app.services.auth_service import hash_password


load_dotenv()

DEMO_PASSWORD = os.getenv("DEMO_USER_PASSWORD")

if not DEMO_PASSWORD:
    raise RuntimeError(
        "DEMO_USER_PASSWORD must be configured in .env "
        "before running session plan CRUD tests."
    )


client = TestClient(app)

TEST_PDF = (
    b"%PDF-1.4\n"
    b"1 0 obj<</Type/Catalog>>endobj\n"
    b"trailer<</Root 1 0 R>>\n"
    b"%%EOF"
)


@pytest.fixture(scope="module", autouse=True)
def session_plan_test_environment():
    """
    Provision isolated TEST schools, class divisions and
    Para-Teacher accounts for the session-plan CRUD test module.
    """
    db = SessionLocal()
    suffix = uuid.uuid4().hex[:12]
    password = DEMO_PASSWORD

    school_ids = []
    teacher_ids = []

    school_codes = {
        "PT001": f"TST-P1-{suffix}",
        "PT002": f"TST-P2-{suffix}",
        "PT003": f"TST-P3-{suffix}",
        "PT004": f"TST-P4-{suffix}",
    }

    emails = {
        code: f"{code.lower()}-{suffix}@test.vigyan.com"
        for code in PARA_TEACHERS
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

        for code, school_code in school_codes.items():
            school = School(
                school_code=school_code,
                school_name=f"Session Plan {code} Test School",
                status="ACTIVE",
                data_origin="TEST",
            )
            db.add(school)
            db.flush()

            school_ids.append(school.id)

            # PT001 needs two divisions for the ordering test.
            division_names = (
                ["A", "B"] if code == "PT001" else ["A"]
            )

            for division_name in division_names:
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
                user_code=f"{code}-{suffix}",
                account_category="PARA_TEACHER",
                full_name=f"Session Plan Test {code}",
                email=emails[code],
                password_hash=hash_password(password),
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

            PARA_TEACHERS[code]["email"] = emails[code]
            PARA_TEACHERS[code]["school_code"] = school_code

        db.commit()

        print(
            "\nCreated isolated TEST session-plan environment "
            f"({suffix})."
        )

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()

    yield

    # Teardown: remove planning data before users and schools.
    _cleanup_session_plan_state()

    cleanup_db = SessionLocal()

    try:
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
            "\nRemoved isolated TEST session-plan environment."
        )

    except Exception:
        cleanup_db.rollback()
        raise

    finally:
        cleanup_db.close()


def create_cross_teacher_content_and_attachment(
    context,
    storage: SessionPlanAttachmentStorage,
):
    """Create test-only lesson content and a real temporary PDF attachment."""
    db = SessionLocal()
    storage_key = None

    try:
        content = SessionPlanContent(
            session_plan_item_id=uuid.UUID(context["item_id"]),
            content="Original test lesson-plan content.",
            data_origin="TEST",
        )
        db.add(content)
        db.flush()

        storage_key = storage.save(
            "test-attachment.pdf",
            "application/pdf",
            TEST_PDF,
        )

        attachment = SessionPlanAttachment(
            session_plan_content_id=content.id,
            storage_key=storage_key,
            original_filename="test-attachment.pdf",
            content_type="application/pdf",
            file_size_bytes=len(TEST_PDF),
            data_origin="TEST",
        )
        db.add(attachment)
        db.commit()
        db.refresh(content)
        db.refresh(attachment)

        return {
            "content_id": str(content.id),
            "attachment_id": str(attachment.id),
            "storage_key": storage_key,
        }

    except Exception:
        db.rollback()

        if storage_key:
            storage.delete(storage_key)

        raise

    finally:
        db.close()


PARA_TEACHERS = {
    "PT001": {"email": None, "school_code": None},
    "PT002": {"email": None, "school_code": None},
    "PT003": {"email": None, "school_code": None},
    "PT004": {"email": None, "school_code": None},
}


@pytest.fixture
def temporary_cross_teacher_context():
    """
    Create isolated TEST records for cross-teacher authorization tests.

    Creates:
    - One TEST school and class division.
    - One TEST para-teacher with a school assignment.
    - One TEST project-wide Data Manager.
    - One session-plan week and item.

    All records created here are removed during teardown.
    """
    db = SessionLocal()

    suffix = uuid.uuid4().hex[:12]

    teacher_email = f"pt-session-plan-{suffix}@test.vigyan.com"
    manager_email = f"dm-session-plan-{suffix}@test.vigyan.com"

    teacher_password = f"Test-PT-{uuid.uuid4().hex}-Password"
    manager_password = f"Test-DM-{uuid.uuid4().hex}-Password"

    week_start = date(2026, 9, 21)
    week_end = date(2026, 9, 27)

    try:
        teacher_role = (
            db.query(Role)
            .filter(Role.code == "PARA_TEACHER")
            .first()
        )
        manager_role = (
            db.query(Role)
            .filter(Role.code == "DATA_MANAGER")
            .first()
        )

        assert teacher_role is not None, "PARA_TEACHER role must be seeded."
        assert manager_role is not None, "DATA_MANAGER role must be seeded."

        school = School(
            school_code=f"TST-{suffix}",
            school_name=f"Session Plan Test School {suffix}",
            status="ACTIVE",
            data_origin="TEST",
        )
        db.add(school)
        db.flush()

        division = ClassDivision(
            school_id=school.id,
            class_level=5,
            division="A",
            status="ACTIVE",
            data_origin="TEST",
        )
        db.add(division)

        teacher = User(
            user_code=f"PT-TEST-{suffix}",
            account_category="PARA_TEACHER",
            full_name="Session Plan Test Teacher",
            email=teacher_email,
            password_hash=hash_password(teacher_password),
            status="ACTIVE",
            data_origin="TEST",
        )

        manager = User(
            user_code=f"DM-TEST-{suffix}",
            account_category="DATA_MANAGER",
            full_name="Session Plan Test Data Manager",
            email=manager_email,
            password_hash=hash_password(manager_password),
            status="ACTIVE",
            data_origin="TEST",
        )

        db.add_all([teacher, manager])
        db.flush()

        db.add_all([
            UserRole(
                user_id=teacher.id,
                role_id=teacher_role.id,
                is_active=True,
            ),
            UserRole(
                user_id=manager.id,
                role_id=manager_role.id,
                is_active=True,
            ),
            UserAssignment(
                user_id=teacher.id,
                scope_type="SCHOOL",
                school_id=school.id,
                start_date=week_start,
                end_date=None,
                is_active=True,
            ),
        ])

        week = SessionPlanWeek(
            para_teacher_id=teacher.id,
            week_start_date=week_start,
            week_end_date=week_end,
            data_origin="TEST",
        )
        db.add(week)
        db.flush()

        item = SessionPlanItem(
            session_plan_week_id=week.id,
            class_division_id=division.id,
            planned_date=week_start,
            sequence_no=1,
            data_origin="TEST",
        )
        db.add(item)

        db.commit()

        context = {
            "teacher_email": teacher_email,
            "teacher_password": teacher_password,
            "teacher_id": str(teacher.id),
            "manager_email": manager_email,
            "manager_password": manager_password,
            "manager_id": str(manager.id),
            "week_id": str(week.id),
            "item_id": str(item.id),
            "week_start": week_start.isoformat(),
        }

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()

    try:
        yield context

    finally:
        cleanup_db = SessionLocal()


        try:
            cleanup_db.query(SessionPlanAttachment).filter(
                SessionPlanAttachment.session_plan_content_id.in_(
                    cleanup_db.query(SessionPlanContent.id).filter(
                        SessionPlanContent.session_plan_item_id
                        == uuid.UUID(context["item_id"])
                    )
                )
            ).delete(synchronize_session=False)
            # Remove dependent planning records first.
            cleanup_db.query(SessionPlanContent).filter(
                SessionPlanContent.session_plan_item_id == uuid.UUID(context["item_id"])
            ).delete(synchronize_session=False)

            cleanup_db.query(SessionPlanItem).filter(
                SessionPlanItem.id == uuid.UUID(context["item_id"])
            ).delete(synchronize_session=False)

            cleanup_db.query(SessionPlanWeek).filter(
                SessionPlanWeek.id == uuid.UUID(context["week_id"])
            ).delete(synchronize_session=False)

            # Deleting users also cascades their role assignments,
            # school assignments, and authentication sessions.
            cleanup_db.query(User).filter(
                User.id.in_([
                    uuid.UUID(context["teacher_id"]),
                    uuid.UUID(context["manager_id"]),
                ])
            ).delete(synchronize_session=False)

            school = (
                cleanup_db.query(School)
                .filter(School.school_code == f"TST-{suffix}")
                .first()
            )

            if school is not None:
                cleanup_db.query(ClassDivision).filter(
                    ClassDivision.school_id == school.id
                ).delete(synchronize_session=False)

                cleanup_db.delete(school)

            cleanup_db.commit()

        except Exception:
            cleanup_db.rollback()
            raise

        finally:
            cleanup_db.close()

def _cleanup_session_plan_state():
    db = SessionLocal()

    try:
        para_teacher_emails = [
            config["email"]
            for config in PARA_TEACHERS.values()
        ]

        para_teacher_ids = select(User.id).where(
            User.email.in_(para_teacher_emails)
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

        week_ids = [week.id for week in weeks]

        if not week_ids:
            return

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


def login_with_password(email: str, password: str) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": email,
            "password": password,
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


def test_data_manager_can_view_another_teachers_week(
    temporary_cross_teacher_context,
):
    context = temporary_cross_teacher_context

    manager_token = login_with_password(
        context["manager_email"],
        context["manager_password"],
    )

    response = client.get(
        f"/api/v1/session-plans/weeks/{context['week_start']}",
        headers=auth_headers(manager_token),
        params={
            "para_teacher_id": context["teacher_id"],
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["week"]["id"] == context["week_id"]
    assert isinstance(response.json()["items"], list)


def test_data_manager_cannot_update_another_teachers_item(
    temporary_cross_teacher_context,
):
    context = temporary_cross_teacher_context

    manager_token = login_with_password(
        context["manager_email"],
        context["manager_password"],
    )

    response = client.patch(
        f"/api/v1/session-plans/items/{context['item_id']}",
        headers=auth_headers(manager_token),
        json={
            "planned_date": context["week_start"],
        },
    )

    assert response.status_code == 403, response.text
    assert (
        response.json()["detail"]
        == "You cannot modify another para-teacher's plan."
    )


def test_data_manager_can_read_other_teachers_content_and_attachments(
    temporary_cross_teacher_context,
    tmp_path,
    monkeypatch,
):
    context = temporary_cross_teacher_context
    storage = SessionPlanAttachmentStorage(root=tmp_path)

    records = create_cross_teacher_content_and_attachment(
        context,
        storage,
    )

    monkeypatch.setattr(
        session_plan_router,
        "_attachment_storage",
        lambda: storage,
    )

    manager_token = login_with_password(
        context["manager_email"],
        context["manager_password"],
    )
    headers = auth_headers(manager_token)
    item_id = context["item_id"]

    content_response = client.get(
        f"/api/v1/session-plans/items/{item_id}/content",
        headers=headers,
    )

    assert content_response.status_code == 200, content_response.text
    assert content_response.json()["content"] == (
        "Original test lesson-plan content."
    )

    list_response = client.get(
        f"/api/v1/session-plans/items/{item_id}/attachments",
        headers=headers,
    )

    assert list_response.status_code == 200, list_response.text
    assert len(list_response.json()) == 1
    assert list_response.json()[0]["id"] == records["attachment_id"]

    download_response = client.get(
        f"/api/v1/session-plans/items/{item_id}/attachments/"
        f"{records['attachment_id']}",
        headers=headers,
    )

    assert download_response.status_code == 200
    assert download_response.content == TEST_PDF
    assert download_response.headers["content-type"].startswith(
        "application/pdf"
    )


def test_data_manager_cannot_update_other_teachers_content(
    temporary_cross_teacher_context,
    tmp_path,
):
    context = temporary_cross_teacher_context
    storage = SessionPlanAttachmentStorage(root=tmp_path)

    create_cross_teacher_content_and_attachment(context, storage)

    manager_token = login_with_password(
        context["manager_email"],
        context["manager_password"],
    )

    response = client.put(
        f"/api/v1/session-plans/items/{context['item_id']}/content",
        headers=auth_headers(manager_token),
        json={"content": "Unauthorized replacement content."},
    )

    assert response.status_code == 403, response.text

    db = SessionLocal()
    try:
        content = (
            db.query(SessionPlanContent)
            .filter(
                SessionPlanContent.session_plan_item_id
                == uuid.UUID(context["item_id"])
            )
            .one()
        )

        assert content.content == "Original test lesson-plan content."
    finally:
        db.close()


def test_data_manager_cannot_upload_attachment_to_other_teachers_plan(
    temporary_cross_teacher_context,
    tmp_path,
    monkeypatch,
):
    context = temporary_cross_teacher_context
    storage = SessionPlanAttachmentStorage(root=tmp_path)

    records = create_cross_teacher_content_and_attachment(
        context,
        storage,
    )

    monkeypatch.setattr(
        session_plan_router,
        "_attachment_storage",
        lambda: storage,
    )

    manager_token = login_with_password(
        context["manager_email"],
        context["manager_password"],
    )

    response = client.post(
        f"/api/v1/session-plans/items/{context['item_id']}/attachments",
        headers=auth_headers(manager_token),
        files={
            "attachment": (
                "unauthorized.pdf",
                TEST_PDF,
                "application/pdf",
            )
        },
    )

    assert response.status_code == 403, response.text

    # The original attachment remains the only attachment.
    db = SessionLocal()
    try:
        attachments = (
            db.query(SessionPlanAttachment)
            .filter(
                SessionPlanAttachment.session_plan_content_id
                == uuid.UUID(records["content_id"])
            )
            .all()
        )

        assert len(attachments) == 1
        assert attachments[0].id == uuid.UUID(records["attachment_id"])
    finally:
        db.close()

    # The attempted upload must not create another physical file.
    assert len(list(Path(tmp_path).iterdir())) == 1


def test_data_manager_cannot_delete_other_teachers_attachment(
    temporary_cross_teacher_context,
    tmp_path,
    monkeypatch,
):
    context = temporary_cross_teacher_context
    storage = SessionPlanAttachmentStorage(root=tmp_path)

    records = create_cross_teacher_content_and_attachment(
        context,
        storage,
    )

    monkeypatch.setattr(
        session_plan_router,
        "_attachment_storage",
        lambda: storage,
    )

    manager_token = login_with_password(
        context["manager_email"],
        context["manager_password"],
    )

    response = client.delete(
        f"/api/v1/session-plans/items/{context['item_id']}/attachments/"
        f"{records['attachment_id']}",
        headers=auth_headers(manager_token),
    )

    assert response.status_code == 403, response.text

    db = SessionLocal()
    try:
        attachment = (
            db.query(SessionPlanAttachment)
            .filter(
                SessionPlanAttachment.id
                == uuid.UUID(records["attachment_id"])
            )
            .first()
        )

        assert attachment is not None
        assert attachment.storage_key == records["storage_key"]
    finally:
        db.close()

    assert storage.open(records["storage_key"]).read() == TEST_PDF


def test_data_manager_cannot_validate_or_link_other_teachers_item(
    temporary_cross_teacher_context,
):
    context = temporary_cross_teacher_context

    manager_token = login_with_password(
        context["manager_email"],
        context["manager_password"],
    )
    headers = auth_headers(manager_token)
    item_id = context["item_id"]

    validate_response = client.post(
        f"/api/v1/session-plans/items/{item_id}/validate",
        headers=headers,
    )

    assert validate_response.status_code == 403, validate_response.text

    link_response = client.post(
        f"/api/v1/session-plans/items/{item_id}/teaching-session",
        headers=headers,
    )

    assert link_response.status_code == 403, link_response.text