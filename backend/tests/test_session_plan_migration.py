import uuid
from datetime import date, time, timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from app.database import SessionLocal
from app.models import (
    ClassDivision,
    SessionPlanContent,
    SessionPlanItem,
    SessionPlanWeek,
    TeachingSession,
    User,
)


def monday_for_test(test_name: str) -> date:
    """
    Generate a deterministic-but-unique Monday for each test.

    This prevents migration tests from colliding with rows that may already
    exist in the development/test database.
    """
    base = date(2030, 1, 7)  # Monday

    offset = abs(hash(test_name)) % (52 * 20)

    return base + timedelta(weeks=offset)


@pytest.fixture
def db():
    session = SessionLocal()

    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def week_dates(request):
    """
    Return an isolated Monday/Sunday/next-Monday set for the current test.
    """
    monday = monday_for_test(request.node.nodeid)
    sunday = monday + timedelta(days=6)
    next_monday = monday + timedelta(days=7)

    return monday, sunday, next_monday


@pytest.fixture
def existing_users(db):
    users = (
        db.query(User)
        .order_by(User.id)
        .limit(2)
        .all()
    )

    assert len(users) >= 2, (
        "Migration tests require at least two existing users "
        "for teacher foreign-key targets."
    )

    return users[0], users[1]


@pytest.fixture
def existing_class_division(db):
    class_division = (
        db.query(ClassDivision)
        .order_by(ClassDivision.id)
        .first()
    )

    assert class_division is not None, (
        "Migration tests require an existing class division "
        "for the session-plan item foreign key."
    )

    return class_division


def flush_and_commit(db):
    """
    Despite the historical name, this only flushes.

    The fixture rolls the transaction back after every test.
    """
    db.flush()


def assert_integrity_error(db, operation):
    with pytest.raises(IntegrityError):
        operation()

    db.rollback()


def make_week(
    teacher_id,
    *,
    week_start,
    week_end,
):
    return SessionPlanWeek(
        para_teacher_id=teacher_id,
        week_start_date=week_start,
        week_end_date=week_end,
    )


def make_item(
    week_id,
    class_division_id,
    *,
    sequence_no=1,
    planned_date,
    planned_start_time=None,
    planned_end_time=None,
):
    return SessionPlanItem(
        session_plan_week_id=week_id,
        class_division_id=class_division_id,
        planned_date=planned_date,
        planned_start_time=planned_start_time,
        planned_end_time=planned_end_time,
        sequence_no=sequence_no,
    )


def make_content(item_id):
    return SessionPlanContent(
        session_plan_item_id=item_id,
        content="Fractions and equivalent fractions",
    )


def test_monday_week_start_is_accepted(
    db,
    existing_users,
    week_dates,
):
    teacher, _ = existing_users
    monday, sunday, _ = week_dates

    week = make_week(
        teacher.id,
        week_start=monday,
        week_end=sunday,
    )

    db.add(week)
    flush_and_commit(db)

    assert week.id is not None


def test_sunday_week_end_is_accepted_for_monday_start(
    db,
    existing_users,
    week_dates,
):
    teacher, _ = existing_users
    monday, sunday, _ = week_dates

    week = make_week(
        teacher.id,
        week_start=monday,
        week_end=sunday,
    )

    db.add(week)
    flush_and_commit(db)

    assert week.id is not None


def test_non_monday_week_start_is_rejected(
    db,
    existing_users,
    week_dates,
):
    teacher, _ = existing_users
    monday, _, _ = week_dates

    non_monday = monday + timedelta(days=1)
    week_end = non_monday + timedelta(days=6)

    week = make_week(
        teacher.id,
        week_start=non_monday,
        week_end=week_end,
    )

    db.add(week)

    assert_integrity_error(db, db.flush)


def test_incorrect_week_end_is_rejected(
    db,
    existing_users,
    week_dates,
):
    teacher, _ = existing_users
    monday, _, _ = week_dates

    week = make_week(
        teacher.id,
        week_start=monday,
        week_end=monday + timedelta(days=5),
    )

    db.add(week)

    assert_integrity_error(db, db.flush)


def test_duplicate_teacher_week_is_rejected(
    db,
    existing_users,
    week_dates,
):
    teacher, _ = existing_users
    monday, sunday, _ = week_dates

    first = make_week(
        teacher.id,
        week_start=monday,
        week_end=sunday,
    )

    db.add(first)
    db.flush()

    duplicate = make_week(
        teacher.id,
        week_start=monday,
        week_end=sunday,
    )

    db.add(duplicate)

    assert_integrity_error(db, db.flush)


def test_same_week_for_different_teachers_is_allowed(
    db,
    existing_users,
    week_dates,
):
    teacher_one, teacher_two = existing_users
    monday, sunday, _ = week_dates

    first = make_week(
        teacher_one.id,
        week_start=monday,
        week_end=sunday,
    )

    second = make_week(
        teacher_two.id,
        week_start=monday,
        week_end=sunday,
    )

    db.add_all([first, second])
    flush_and_commit(db)

    assert first.id != second.id


def test_duplicate_item_sequence_within_week_is_rejected(
    db,
    existing_users,
    existing_class_division,
    week_dates,
):
    teacher, _ = existing_users
    monday, sunday, _ = week_dates

    week = make_week(
        teacher.id,
        week_start=monday,
        week_end=sunday,
    )

    db.add(week)
    db.flush()

    first = make_item(
        week.id,
        existing_class_division.id,
        sequence_no=1,
        planned_date=monday,
    )

    db.add(first)
    db.flush()

    duplicate = make_item(
        week.id,
        existing_class_division.id,
        sequence_no=1,
        planned_date=monday,
    )

    db.add(duplicate)

    assert_integrity_error(db, db.flush)


def test_same_sequence_in_different_weeks_is_allowed(
    db,
    existing_users,
    existing_class_division,
    week_dates,
):
    teacher, _ = existing_users
    monday, sunday, next_monday = week_dates
    next_sunday = next_monday + timedelta(days=6)

    first_week = make_week(
        teacher.id,
        week_start=monday,
        week_end=sunday,
    )

    second_week = make_week(
        teacher.id,
        week_start=next_monday,
        week_end=next_sunday,
    )

    db.add_all([first_week, second_week])
    db.flush()

    first_item = make_item(
        first_week.id,
        existing_class_division.id,
        sequence_no=1,
        planned_date=monday,
    )

    second_item = make_item(
        second_week.id,
        existing_class_division.id,
        sequence_no=1,
        planned_date=next_monday,
    )

    db.add_all([first_item, second_item])
    flush_and_commit(db)

    assert first_item.id != second_item.id


@pytest.mark.parametrize(
    "sequence_no",
    [0, -1],
)
def test_non_positive_sequence_is_rejected(
    db,
    existing_users,
    existing_class_division,
    week_dates,
    sequence_no,
):
    teacher, _ = existing_users
    monday, sunday, _ = week_dates

    week = make_week(
        teacher.id,
        week_start=monday,
        week_end=sunday,
    )

    db.add(week)
    db.flush()

    item = make_item(
        week.id,
        existing_class_division.id,
        sequence_no=sequence_no,
        planned_date=monday,
    )

    db.add(item)

    assert_integrity_error(db, db.flush)


@pytest.mark.parametrize(
    "start_time,end_time",
    [
        (time(9, 0), None),
        (None, time(10, 0)),
        (time(10, 0), time(9, 0)),
        (time(9, 0), time(9, 0)),
    ],
)
def test_invalid_planned_time_pair_is_rejected(
    db,
    existing_users,
    existing_class_division,
    week_dates,
    start_time,
    end_time,
):
    teacher, _ = existing_users
    monday, sunday, _ = week_dates

    week = make_week(
        teacher.id,
        week_start=monday,
        week_end=sunday,
    )

    db.add(week)
    db.flush()

    item = make_item(
        week.id,
        existing_class_division.id,
        planned_date=monday,
        planned_start_time=start_time,
        planned_end_time=end_time,
    )

    db.add(item)

    assert_integrity_error(db, db.flush)


def test_one_plan_item_can_exist_without_content(
    db,
    existing_users,
    existing_class_division,
    week_dates,
):
    teacher, _ = existing_users
    monday, sunday, _ = week_dates

    week = make_week(
        teacher.id,
        week_start=monday,
        week_end=sunday,
    )

    db.add(week)
    db.flush()

    item = make_item(
        week.id,
        existing_class_division.id,
        planned_date=monday,
    )

    db.add(item)
    flush_and_commit(db)

    assert item.id is not None


def test_one_content_per_item_is_enforced(
    db,
    existing_users,
    existing_class_division,
    week_dates,
):
    teacher, _ = existing_users
    monday, sunday, _ = week_dates

    week = make_week(
        teacher.id,
        week_start=monday,
        week_end=sunday,
    )

    db.add(week)
    db.flush()

    item = make_item(
        week.id,
        existing_class_division.id,
        planned_date=monday,
    )

    db.add(item)
    db.flush()

    content = make_content(item.id)

    db.add(content)
    flush_and_commit(db)

    assert content.id is not None


def test_duplicate_content_for_item_is_rejected(
    db,
    existing_users,
    existing_class_division,
    week_dates,
):
    teacher, _ = existing_users
    monday, sunday, _ = week_dates

    week = make_week(
        teacher.id,
        week_start=monday,
        week_end=sunday,
    )

    db.add(week)
    db.flush()

    item = make_item(
        week.id,
        existing_class_division.id,
        planned_date=monday,
    )

    db.add(item)
    db.flush()

    first = make_content(item.id)

    db.add(first)
    db.flush()

    duplicate = make_content(item.id)

    db.add(duplicate)

    assert_integrity_error(db, db.flush)


def test_teaching_session_plan_item_id_may_be_null(
    db,
    existing_users,
    existing_class_division,
    week_dates,
):
    teacher, _ = existing_users
    monday, _, _ = week_dates

    session = TeachingSession(
        class_division_id=existing_class_division.id,
        para_teacher_id=teacher.id,
        session_date=monday,
        session_plan_item_id=None,
    )

    db.add(session)
    flush_and_commit(db)

    assert session.id is not None
    assert session.session_plan_item_id is None


def test_two_teaching_sessions_cannot_reference_same_plan_item(
    db,
    existing_users,
    existing_class_division,
    week_dates,
):
    teacher, _ = existing_users
    monday, sunday, next_monday = week_dates

    week = make_week(
        teacher.id,
        week_start=monday,
        week_end=sunday,
    )

    db.add(week)
    db.flush()

    item = make_item(
        week.id,
        existing_class_division.id,
        planned_date=monday,
    )

    db.add(item)
    db.flush()

    first_session = TeachingSession(
        class_division_id=existing_class_division.id,
        para_teacher_id=teacher.id,
        session_date=monday,
        session_plan_item_id=item.id,
    )

    db.add(first_session)
    db.flush()

    duplicate_session = TeachingSession(
        class_division_id=existing_class_division.id,
        para_teacher_id=teacher.id,
        session_date=next_monday,
        session_plan_item_id=item.id,
    )

    db.add(duplicate_session)

    assert_integrity_error(db, db.flush)


def test_nonexistent_session_plan_week_fk_is_rejected(
    db,
    existing_class_division,
    week_dates,
):
    monday, _, _ = week_dates

    item = SessionPlanItem(
        session_plan_week_id=uuid.uuid4(),
        class_division_id=existing_class_division.id,
        planned_date=monday,
        sequence_no=1,
    )

    db.add(item)

    assert_integrity_error(db, db.flush)


def test_nonexistent_session_plan_item_fk_for_content_is_rejected(
    db,
):
    content = SessionPlanContent(
        session_plan_item_id=uuid.uuid4(),
        content="Invalid target",
    )

    db.add(content)

    assert_integrity_error(db, db.flush)


def test_nonexistent_session_plan_item_fk_for_teaching_session_is_rejected(
    db,
    existing_users,
    existing_class_division,
    week_dates,
):
    teacher, _ = existing_users
    monday, _, _ = week_dates

    session = TeachingSession(
        class_division_id=existing_class_division.id,
        para_teacher_id=teacher.id,
        session_date=monday,
        session_plan_item_id=uuid.uuid4(),
    )

    db.add(session)

    assert_integrity_error(db, db.flush)


def test_nonexistent_class_division_fk_is_rejected(
    db,
    existing_users,
    week_dates,
):
    teacher, _ = existing_users
    monday, sunday, _ = week_dates

    week = make_week(
        teacher.id,
        week_start=monday,
        week_end=sunday,
    )

    db.add(week)
    db.flush()

    item = SessionPlanItem(
        session_plan_week_id=week.id,
        class_division_id=uuid.uuid4(),
        planned_date=monday,
        sequence_no=1,
    )

    db.add(item)

    assert_integrity_error(db, db.flush)