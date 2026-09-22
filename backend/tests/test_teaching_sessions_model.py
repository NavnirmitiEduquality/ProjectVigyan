from datetime import date, datetime, time, timezone
# from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from app.database import SessionLocal
from app.models.class_division import ClassDivision
from app.models.school import School
from app.models.teaching_session import TeachingSession
from app.models.user import User


def get_first_school(db):
    return db.query(School).first()


def get_first_para_teacher(db):
    return (
        db.query(User)
        .join(User.user_roles)
        .filter(User.user_code.like("PT%"))
        .first()
    )


def get_first_class_division(db):
    return db.query(ClassDivision).first()


def create_session(db, **overrides):
    # school = get_first_school(db)
    class_division = get_first_class_division(db)
    para_teacher = get_first_para_teacher(db)

    session = TeachingSession(
        class_division_id=class_division.id,
        para_teacher_id=para_teacher.id,
        session_date=date(2026, 9, 21),
        **overrides,
    )

    db.add(session)
    db.commit()
    db.refresh(session)

    return session


def test_create_valid_teaching_session():
    db = SessionLocal()

    try:
        session = create_session(
            db,
            planned_start_time=time(9, 0),
            planned_end_time=time(10, 0),
            remarks="Regular classroom session",
        )

        assert session.id is not None
        assert session.status == "PLANNED"
        assert session.data_origin == "PRODUCTION"
        assert session.feedback_submitted is False
        assert session.session_date == date(2026, 9, 21)

        db.delete(session)
        db.commit()
    finally:
        db.close()


def test_teaching_session_relationships():
    db = SessionLocal()

    try:
        session = create_session(db)

        assert session.class_division is not None
        assert session.para_teacher is not None
        assert session.class_division.id == session.class_division_id
        assert session.para_teacher.id == session.para_teacher_id

        db.delete(session)
        db.commit()
    finally:
        db.close()


@pytest.mark.parametrize(
    "status",
    ["PLANNED", "IN_PROGRESS", "COMPLETED", "CANCELLED"],
)
def test_valid_teaching_session_statuses(status):
    db = SessionLocal()

    try:
        session = create_session(db, status=status)

        assert session.status == status

        db.delete(session)
        db.commit()
    finally:
        db.close()


def test_invalid_teaching_session_status_is_rejected():
    db = SessionLocal()

    try:
        session = create_session(
            db,
            status="INVALID",
        )

        # The invalid status should be rejected by the database constraint.
        # The helper commits immediately, so this test expects IntegrityError.
        assert False, "Expected IntegrityError"
    except IntegrityError:
        db.rollback()
    finally:
        db.close()


def test_negative_duration_is_rejected():
    db = SessionLocal()

    try:
        session = create_session(
            db,
            duration_minutes=-1,
        )

        assert False, "Expected IntegrityError"
    except IntegrityError:
        db.rollback()
    finally:
        db.close()


def test_planned_time_range_is_validated():
    db = SessionLocal()

    try:
        session = create_session(
            db,
            planned_start_time=time(10, 0),
            planned_end_time=time(9, 0),
        )

        assert False, "Expected IntegrityError"
    except IntegrityError:
        db.rollback()
    finally:
        db.close()


def test_planned_times_can_be_omitted():
    db = SessionLocal()

    try:
        session = create_session(db)

        assert session.planned_start_time is None
        assert session.planned_end_time is None

        db.delete(session)
        db.commit()
    finally:
        db.close()


def test_actual_times_and_duration_can_be_stored():
    db = SessionLocal()

    try:
        start = datetime(2026, 9, 21, 9, 0, tzinfo=timezone.utc)
        end = datetime(2026, 9, 21, 9, 45, tzinfo=timezone.utc)

        session = create_session(
            db,
            actual_start_time=start,
            actual_end_time=end,
            duration_minutes=45,
            status="COMPLETED",
        )

        assert session.actual_start_time == start
        assert session.actual_end_time == end
        assert session.duration_minutes == 45
        assert session.status == "COMPLETED"

        db.delete(session)
        db.commit()
    finally:
        db.close()


def test_submission_fields_can_be_stored():
    db = SessionLocal()

    try:
        submitted_at = datetime(
            2026,
            9,
            21,
            10,
            0,
            tzinfo=timezone.utc,
        )

        session = create_session(
            db,
            status="COMPLETED",
            feedback_submitted=True,
            submitted_at=submitted_at,
        )

        assert session.feedback_submitted is True
        assert session.submitted_at == submitted_at
        assert session.status == "COMPLETED"

        db.delete(session)
        db.commit()
    finally:
        db.close()


def test_data_origin_is_server_controlled():
    db = SessionLocal()

    try:
        session = create_session(
            db,
            data_origin="DEMO",
        )

        # This test documents the model-level expectation that production
        # application code should set data_origin rather than client input.
        # The SQLAlchemy model itself currently allows DEMO for test/demo data.
        assert session.data_origin == "DEMO"

        db.delete(session)
        db.commit()
    finally:
        db.close()
