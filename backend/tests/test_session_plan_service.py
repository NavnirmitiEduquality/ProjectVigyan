from datetime import date, time, timedelta
from uuid import uuid4
import pytest

from app.models import (
    ClassDivision,
    SessionPlanContent,
    SessionPlanItem,
    SessionPlanWeek,
    TeachingSession,
    User,
    UserAssignment,
)
from app.database import SessionLocal
from app.services.session_plan.service import (
    DuplicatePlanningItemError,
    InvalidPlanningDateError,
    InvalidPlanningWeekError,
    MinimumWeeklySessionsError,
    MissingLessonPlanContentError,
    SessionPlanAccessError,
    SessionPlanItemLockedError,
    SessionPlanService,
)

@pytest.fixture
def db():
    session = SessionLocal()

    try:
        yield session
    finally:
        session.rollback()
        session.close()

def get_demo_class_divisions(db, count=7):
    divisions = (
        db.query(ClassDivision)
        .filter(ClassDivision.data_origin == "DEMO")
        .order_by(ClassDivision.id)
        .limit(count)
        .all()
    )

    if len(divisions) < count:
        pytest.skip(
            f"Need at least {count} DEMO class divisions."
        )

    return divisions


def create_para_teacher(
    db,
    *,
    school_id,
    start_date=date(2026, 1, 1),
    end_date=None,
):
    user = User(
        user_code=f"TEST-PT-{uuid4().hex[:10]}",
        full_name="Session Plan Test Teacher",
        email=f"session-plan-{uuid4().hex}@example.test",
        password_hash="test-password-hash",
        status="ACTIVE",
        data_origin="TEST",
    )

    db.add(user)
    db.flush()

    assignment = UserAssignment(
        user_id=user.id,
        scope_type="SCHOOL",
        school_id=school_id,
        start_date=start_date,
        end_date=end_date,
        is_active=True,
    )

    db.add(assignment)
    db.flush()

    return user


def monday():
    return date(2026, 9, 21)


def test_create_week_requires_monday(db):
    service = SessionPlanService()

    divisions = get_demo_class_divisions(db, 1)

    teacher = create_para_teacher(
        db,
        school_id=divisions[0].school_id,
    )

    with pytest.raises(InvalidPlanningWeekError):
        service.get_or_create_week(
            db,
            para_teacher_id=teacher.id,
            week_start_date=date(2026, 9, 22),
            data_origin="TEST",
        )


def test_create_week_creates_monday_to_sunday_week(db):
    service = SessionPlanService()

    divisions = get_demo_class_divisions(db, 1)

    teacher = create_para_teacher(
        db,
        school_id=divisions[0].school_id,
    )

    week = service.get_or_create_week(
        db,
        para_teacher_id=teacher.id,
        week_start_date=monday(),
        data_origin="TEST",
    )

    assert week.week_start_date == monday()
    assert week.week_end_date == monday() + timedelta(days=6)
    assert week.para_teacher_id == teacher.id


def test_create_week_is_idempotent(db):
    service = SessionPlanService()

    divisions = get_demo_class_divisions(db, 1)

    teacher = create_para_teacher(
        db,
        school_id=divisions[0].school_id,
    )

    first = service.get_or_create_week(
        db,
        para_teacher_id=teacher.id,
        week_start_date=monday(),
        data_origin="TEST",
    )

    second = service.get_or_create_week(
        db,
        para_teacher_id=teacher.id,
        week_start_date=monday(),
        data_origin="TEST",
    )

    assert first.id == second.id


def test_create_item_rejects_date_outside_week(db):
    service = SessionPlanService()

    divisions = get_demo_class_divisions(db, 1)

    teacher = create_para_teacher(
        db,
        school_id=divisions[0].school_id,
    )

    week = service.get_or_create_week(
        db,
        para_teacher_id=teacher.id,
        week_start_date=monday(),
        data_origin="TEST",
    )

    with pytest.raises(InvalidPlanningDateError):
        service.create_item(
            db,
            para_teacher_id=teacher.id,
            session_plan_week_id=week.id,
            class_division_id=divisions[0].id,
            planned_date=monday() + timedelta(days=7),
            sequence_no=1,
            data_origin="TEST",
        )


def test_create_item_rejects_unauthorized_school(db):
    service = SessionPlanService()

    divisions = get_demo_class_divisions(db, 2)

    teacher = create_para_teacher(
        db,
        school_id=divisions[0].school_id,
    )

    week = service.get_or_create_week(
        db,
        para_teacher_id=teacher.id,
        week_start_date=monday(),
        data_origin="TEST",
    )

    if divisions[0].school_id == divisions[1].school_id:
        pytest.skip("Need DEMO divisions from different schools.")

    with pytest.raises(SessionPlanAccessError):
        service.create_item(
            db,
            para_teacher_id=teacher.id,
            session_plan_week_id=week.id,
            class_division_id=divisions[1].id,
            planned_date=monday(),
            sequence_no=1,
            data_origin="TEST",
        )


def test_same_class_cannot_be_planned_twice_on_same_date(db):
    service = SessionPlanService()

    divisions = get_demo_class_divisions(db, 1)

    teacher = create_para_teacher(
        db,
        school_id=divisions[0].school_id,
    )

    week = service.get_or_create_week(
        db,
        para_teacher_id=teacher.id,
        week_start_date=monday(),
        data_origin="TEST",
    )

    service.create_item(
        db,
        para_teacher_id=teacher.id,
        session_plan_week_id=week.id,
        class_division_id=divisions[0].id,
        planned_date=monday(),
        sequence_no=1,
        data_origin="TEST",
    )

    with pytest.raises(DuplicatePlanningItemError):
        service.create_item(
            db,
            para_teacher_id=teacher.id,
            session_plan_week_id=week.id,
            class_division_id=divisions[0].id,
            planned_date=monday(),
            sequence_no=2,
            data_origin="TEST",
        )


def test_week_requires_at_least_six_items(db):
    service = SessionPlanService()

    divisions = get_demo_class_divisions(db, 7)

    teacher = create_para_teacher(
        db,
        school_id=divisions[0].school_id,
    )

    usable_divisions = [
        division
        for division in divisions
        if division.school_id == divisions[0].school_id
    ]

    if len(usable_divisions) < 6:
        pytest.skip(
            "Need six class divisions in the same school."
        )

    week = service.get_or_create_week(
        db,
        para_teacher_id=teacher.id,
        week_start_date=monday(),
        data_origin="TEST",
    )

    for index, division in enumerate(usable_divisions[:5], start=1):
        service.create_item(
            db,
            para_teacher_id=teacher.id,
            session_plan_week_id=week.id,
            class_division_id=division.id,
            planned_date=monday() + timedelta(days=index - 1),
            sequence_no=index,
            data_origin="TEST",
        )

    with pytest.raises(MinimumWeeklySessionsError):
        service.validate_week(
            db,
            week=week,
        )


def test_week_with_six_items_is_valid(db):
    service = SessionPlanService()

    divisions = get_demo_class_divisions(db, 7)

    teacher = create_para_teacher(
        db,
        school_id=divisions[0].school_id,
    )

    usable_divisions = [
        division
        for division in divisions
        if division.school_id == divisions[0].school_id
    ]

    if len(usable_divisions) < 6:
        pytest.skip(
            "Need six class divisions in the same school."
        )

    week = service.get_or_create_week(
        db,
        para_teacher_id=teacher.id,
        week_start_date=monday(),
        data_origin="TEST",
    )

    for index, division in enumerate(usable_divisions[:6], start=1):
        service.create_item(
            db,
            para_teacher_id=teacher.id,
            session_plan_week_id=week.id,
            class_division_id=division.id,
            planned_date=monday() + timedelta(days=index - 1),
            sequence_no=index,
            data_origin="TEST",
        )

    assert service.validate_week(
        db,
        week=week,
    ) is week


def test_lesson_plan_content_is_required_before_teaching_session_link(db):
    service = SessionPlanService()

    divisions = get_demo_class_divisions(db, 7)

    teacher = create_para_teacher(
        db,
        school_id=divisions[0].school_id,
    )

    usable_divisions = [
        division
        for division in divisions
        if division.school_id == divisions[0].school_id
    ]

    if len(usable_divisions) < 6:
        pytest.skip(
            "Need six class divisions in the same school."
        )

    week = service.get_or_create_week(
        db,
        para_teacher_id=teacher.id,
        week_start_date=monday(),
        data_origin="TEST",
    )

    first_item = None

    for index, division in enumerate(usable_divisions[:6], start=1):
        item = service.create_item(
            db,
            para_teacher_id=teacher.id,
            session_plan_week_id=week.id,
            class_division_id=division.id,
            planned_date=monday() + timedelta(days=index - 1),
            sequence_no=index,
            data_origin="TEST",
        )

        if index == 1:
            first_item = item

    with pytest.raises(MissingLessonPlanContentError):
        service.ensure_ready_for_teaching_session(
            db,
            para_teacher_id=teacher.id,
            item_id=first_item.id,
        )


def test_lesson_plan_content_allows_teaching_session_readiness(db):
    service = SessionPlanService()

    divisions = get_demo_class_divisions(db, 7)

    teacher = create_para_teacher(
        db,
        school_id=divisions[0].school_id,
    )

    usable_divisions = [
        division
        for division in divisions
        if division.school_id == divisions[0].school_id
    ]

    if len(usable_divisions) < 6:
        pytest.skip(
            "Need six class divisions in the same school."
        )

    week = service.get_or_create_week(
        db,
        para_teacher_id=teacher.id,
        week_start_date=monday(),
        data_origin="TEST",
    )

    first_item = None

    for index, division in enumerate(usable_divisions[:6], start=1):
        item = service.create_item(
            db,
            para_teacher_id=teacher.id,
            session_plan_week_id=week.id,
            class_division_id=division.id,
            planned_date=monday() + timedelta(days=index - 1),
            sequence_no=index,
            data_origin="TEST",
        )

        if index == 1:
            first_item = item

    service.set_content(
        db,
        para_teacher_id=teacher.id,
        item_id=first_item.id,
        content="Lesson plan for the planned session.",
        data_origin="TEST",
    )

    ready = service.ensure_ready_for_teaching_session(
        db,
        para_teacher_id=teacher.id,
        item_id=first_item.id,
    )

    assert ready.id == first_item.id


def test_plan_item_can_be_edited_before_session_starts(db):
    service = SessionPlanService()

    divisions = get_demo_class_divisions(db, 1)

    teacher = create_para_teacher(
        db,
        school_id=divisions[0].school_id,
    )

    week = service.get_or_create_week(
        db,
        para_teacher_id=teacher.id,
        week_start_date=monday(),
        data_origin="TEST",
    )

    item = service.create_item(
        db,
        para_teacher_id=teacher.id,
        session_plan_week_id=week.id,
        class_division_id=divisions[0].id,
        planned_date=monday(),
        sequence_no=1,
        data_origin="TEST",
    )

    updated = service.update_item(
        db,
        para_teacher_id=teacher.id,
        item_id=item.id,
        planned_start_time=time(10, 0),
        planned_end_time=time(10, 45),
    )

    assert updated.planned_start_time == time(10, 0)
    assert updated.planned_end_time == time(10, 45)


def test_plan_item_is_locked_after_teaching_session_starts(db):
    service = SessionPlanService()

    divisions = get_demo_class_divisions(db, 1)

    teacher = create_para_teacher(
        db,
        school_id=divisions[0].school_id,
    )

    week = service.get_or_create_week(
        db,
        para_teacher_id=teacher.id,
        week_start_date=monday(),
        data_origin="TEST",
    )

    item = service.create_item(
        db,
        para_teacher_id=teacher.id,
        session_plan_week_id=week.id,
        class_division_id=divisions[0].id,
        planned_date=monday(),
        sequence_no=1,
        data_origin="TEST",
    )

    session = TeachingSession(
        class_division_id=divisions[0].id,
        para_teacher_id=teacher.id,
        session_plan_item_id=item.id,
        session_date=item.planned_date,
        planned_start_time=item.planned_start_time,
        planned_end_time=item.planned_end_time,
        status="IN_PROGRESS",
        data_origin="TEST",
    )

    db.add(session)
    db.flush()

    with pytest.raises(SessionPlanItemLockedError):
        service.update_item(
            db,
            para_teacher_id=teacher.id,
            item_id=item.id,
            planned_start_time=time(11, 0),
            planned_end_time=time(11, 45),
        )