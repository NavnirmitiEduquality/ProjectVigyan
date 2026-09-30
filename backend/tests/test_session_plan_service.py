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
    SessionPlanAlreadyLinkedError,
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

def get_demo_class_divisions(db, count=3):
    rows = (
        db.query(ClassDivision.school_id)
        .filter(ClassDivision.data_origin == "DEMO")
        .group_by(ClassDivision.school_id)
        .order_by(ClassDivision.school_id)
        .all()
    )

    for (school_id,) in rows:
        divisions = (
            db.query(ClassDivision)
            .filter(
                ClassDivision.data_origin == "DEMO",
                ClassDivision.school_id == school_id,
            )
            .order_by(ClassDivision.id)
            .limit(count)
            .all()
        )

        if len(divisions) >= count:
            return divisions

    pytest.skip(
        f"Need at least {count} DEMO class divisions in the same school."
    )


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


def create_six_item_week(
    db,
    service,
    teacher,
    divisions,
):
    usable_divisions = [
        division
        for division in divisions
        if division.school_id == divisions[0].school_id
    ]

    if len(usable_divisions) < 3:
        pytest.skip(
            "Need at least three class divisions in the same school."
        )

    week = service.get_or_create_week(
        db,
        para_teacher_id=teacher.id,
        week_start_date=monday(),
        data_origin="TEST",
    )

    items = []

    for index in range(6):
        division = usable_divisions[index % 3]

        item = service.create_item(
            db,
            para_teacher_id=teacher.id,
            session_plan_week_id=week.id,
            class_division_id=division.id,
            planned_date=monday() + timedelta(days=index),
            sequence_no=index + 1,
            planned_start_time=time(10, 0),
            planned_end_time=time(10, 45),
            data_origin="TEST",
        )

        items.append(item)

    return week, items


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

    school_ids = (
        db.query(ClassDivision.school_id)
        .filter(ClassDivision.data_origin == "DEMO")
        .group_by(ClassDivision.school_id)
        .order_by(ClassDivision.school_id)
        .all()
    )

    if len(school_ids) < 2:
        pytest.skip("Need DEMO divisions from at least two schools.")

    first_school_id = school_ids[0][0]
    second_school_id = school_ids[1][0]

    divisions = (
        db.query(ClassDivision)
        .filter(
            ClassDivision.data_origin == "DEMO",
            ClassDivision.school_id.in_(
                [first_school_id, second_school_id]
            ),
        )
        .order_by(ClassDivision.school_id, ClassDivision.id)
        .all()
    )

    first_division = next(
        division
        for division in divisions
        if division.school_id == first_school_id
    )

    second_division = next(
        division
        for division in divisions
        if division.school_id == second_school_id
    )

    teacher = create_para_teacher(
        db,
        school_id=first_school_id,
    )

    week = service.get_or_create_week(
        db,
        para_teacher_id=teacher.id,
        week_start_date=monday(),
        data_origin="TEST",
    )

    with pytest.raises(SessionPlanAccessError):
        service.create_item(
            db,
            para_teacher_id=teacher.id,
            session_plan_week_id=week.id,
            class_division_id=second_division.id,
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

    divisions = get_demo_class_divisions(db, 3)

    teacher = create_para_teacher(
        db,
        school_id=divisions[0].school_id,
    )

    week, items = create_six_item_week(
        db,
        service,
        teacher,
        divisions,
    )

    # Remove the sixth item so the week contains only five sessions.
    db.delete(items[-1])
    db.flush()

    with pytest.raises(MinimumWeeklySessionsError):
        service.validate_week(
            db,
            week=week,
        )


def test_week_with_six_items_is_valid(db):
    service = SessionPlanService()

    divisions = get_demo_class_divisions(db, 3)

    teacher = create_para_teacher(
        db,
        school_id=divisions[0].school_id,
    )

    week, items = create_six_item_week(
        db,
        service,
        teacher,
        divisions,
    )

    assert len(items) == 6

    assert service.validate_week(
        db,
        week=week,
    ) is week


def test_lesson_plan_content_is_required_before_teaching_session_link(db):
    service = SessionPlanService()

    divisions = get_demo_class_divisions(db, 3)

    teacher = create_para_teacher(
        db,
        school_id=divisions[0].school_id,
    )

    week, items = create_six_item_week(
        db,
        service,
        teacher,
        divisions,
    )

    first_item = items[0]

    with pytest.raises(MissingLessonPlanContentError):
        service.ensure_ready_for_teaching_session(
            db,
            para_teacher_id=teacher.id,
            item_id=first_item.id,
        )


def test_lesson_plan_content_allows_teaching_session_readiness(db):
    service = SessionPlanService()

    divisions = get_demo_class_divisions(db, 3)

    teacher = create_para_teacher(
        db,
        school_id=divisions[0].school_id,
    )

    week, items = create_six_item_week(
        db,
        service,
        teacher,
        divisions,
    )

    first_item = items[0]

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


def test_link_teaching_session_creates_session_from_plan(db):
    service = SessionPlanService()

    divisions = get_demo_class_divisions(db, 3)

    teacher = create_para_teacher(
        db,
        school_id=divisions[0].school_id,
    )

    week, items = create_six_item_week(
        db,
        service,
        teacher,
        divisions,
    )

    first_item = items[0]

    service.set_content(
        db,
        para_teacher_id=teacher.id,
        item_id=first_item.id,
        content="Lesson plan for the planned teaching session.",
        data_origin="TEST",
    )

    teaching_session = service.link_teaching_session(
        db,
        para_teacher_id=teacher.id,
        item_id=first_item.id,
    )

    assert teaching_session.id is not None
    assert teaching_session.session_plan_item_id == first_item.id
    assert teaching_session.class_division_id == first_item.class_division_id
    assert teaching_session.para_teacher_id == teacher.id
    assert teaching_session.session_date == first_item.planned_date
    assert teaching_session.planned_start_time == first_item.planned_start_time
    assert teaching_session.planned_end_time == first_item.planned_end_time
    assert teaching_session.status == "PLANNED"
    assert teaching_session.data_origin == "PRODUCTION"


def test_link_teaching_session_rejects_missing_lesson_content(db):
    service = SessionPlanService()

    divisions = get_demo_class_divisions(db, 3)

    teacher = create_para_teacher(
        db,
        school_id=divisions[0].school_id,
    )

    week, items = create_six_item_week(
        db,
        service,
        teacher,
        divisions,
    )

    first_item = items[0]

    with pytest.raises(MissingLessonPlanContentError):
        service.link_teaching_session(
            db,
            para_teacher_id=teacher.id,
            item_id=first_item.id,
        )

    session_count = (
        db.query(TeachingSession)
        .filter(
            TeachingSession.session_plan_item_id == first_item.id,
        )
        .count()
    )

    assert session_count == 0


def test_link_teaching_session_rejects_wrong_teacher(db):
    service = SessionPlanService()

    divisions = get_demo_class_divisions(db, 3)

    owner = create_para_teacher(
        db,
        school_id=divisions[0].school_id,
    )

    wrong_teacher = create_para_teacher(
        db,
        school_id=divisions[0].school_id,
    )

    week, items = create_six_item_week(
        db,
        service,
        owner,
        divisions,
    )

    first_item = items[0]

    service.set_content(
        db,
        para_teacher_id=owner.id,
        item_id=first_item.id,
        content="Lesson plan content.",
        data_origin="TEST",
    )

    with pytest.raises(SessionPlanAccessError):
        service.link_teaching_session(
            db,
            para_teacher_id=wrong_teacher.id,
            item_id=first_item.id,
        )

    assert (
        db.query(TeachingSession)
        .filter(
            TeachingSession.session_plan_item_id == first_item.id,
        )
        .count()
        == 0
    )


def test_link_teaching_session_rejects_already_linked_item(db):
    service = SessionPlanService()

    divisions = get_demo_class_divisions(db, 3)

    teacher = create_para_teacher(
        db,
        school_id=divisions[0].school_id,
    )

    week, items = create_six_item_week(
        db,
        service,
        teacher,
        divisions,
    )

    first_item = items[0]

    service.set_content(
        db,
        para_teacher_id=teacher.id,
        item_id=first_item.id,
        content="Lesson plan content.",
        data_origin="TEST",
    )

    first_session = service.link_teaching_session(
        db,
        para_teacher_id=teacher.id,
        item_id=first_item.id,
    )

    with pytest.raises(SessionPlanAlreadyLinkedError):
        service.link_teaching_session(
            db,
            para_teacher_id=teacher.id,
            item_id=first_item.id,
        )

    sessions = (
        db.query(TeachingSession)
        .filter(
            TeachingSession.session_plan_item_id == first_item.id,
        )
        .all()
    )

    assert len(sessions) == 1
    assert sessions[0].id == first_session.id


def test_link_teaching_session_flushes_without_commit(db):
    service = SessionPlanService()

    divisions = get_demo_class_divisions(db, 3)

    teacher = create_para_teacher(
        db,
        school_id=divisions[0].school_id,
    )

    week, items = create_six_item_week(
        db,
        service,
        teacher,
        divisions,
    )

    first_item = items[0]

    service.set_content(
        db,
        para_teacher_id=teacher.id,
        item_id=first_item.id,
        content="Lesson plan content.",
        data_origin="TEST",
    )

    teaching_session = service.link_teaching_session(
        db,
        para_teacher_id=teacher.id,
        item_id=first_item.id,
    )

    assert teaching_session.id is not None

    persisted = (
        db.query(TeachingSession)
        .filter(
            TeachingSession.id == teaching_session.id,
        )
        .one()
    )

    assert persisted.id == teaching_session.id