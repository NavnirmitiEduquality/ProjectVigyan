from datetime import date, time

from sqlalchemy import UniqueConstraint
from sqlalchemy.orm import configure_mappers

from app.models import (
    SessionPlanContent,
    SessionPlanItem,
    SessionPlanWeek,
    TeachingSession,
)


def get_check_constraint_names(model):
    return {
        constraint.name
        for constraint in model.__table__.constraints
        if constraint.__class__.__name__ == "CheckConstraint"
    }


def get_unique_constraints(model):
    return {
        constraint.name: tuple(column.name for column in constraint.columns)
        for constraint in model.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    }


def test_session_planning_mappers_configure():
    configure_mappers()


def test_session_plan_week_model_contract():
    table = SessionPlanWeek.__table__

    assert table.name == "session_plan_weeks"

    assert table.c.para_teacher_id.nullable is False
    assert table.c.week_start_date.nullable is False
    assert table.c.week_end_date.nullable is False
    assert table.c.data_origin.nullable is False

    unique_constraints = get_unique_constraints(SessionPlanWeek)

    assert unique_constraints["uq_session_plan_week_teacher_start"] == (
        "para_teacher_id",
        "week_start_date",
    )

    check_constraints = get_check_constraint_names(SessionPlanWeek)

    assert "ck_session_plan_week_monday_start" in check_constraints
    assert "ck_session_plan_week_seven_days" in check_constraints
    assert "ck_session_plan_week_data_origin" in check_constraints


def test_session_plan_week_relationships():
    assert SessionPlanWeek.para_teacher.property.back_populates == (
        "session_plan_weeks"
    )

    assert SessionPlanWeek.items.property.back_populates == (
        "session_plan_week"
    )

    assert SessionPlanWeek.items.property.uselist is True

    cascade = SessionPlanWeek.items.property.cascade

    assert "save-update" in cascade
    assert "delete" in cascade
    assert "delete-orphan" in cascade


def test_session_plan_week_valid_dates_are_representable():
    week = SessionPlanWeek(
        para_teacher_id="00000000-0000-0000-0000-000000000001",
        week_start_date=date(2026, 9, 28),
        week_end_date=date(2026, 10, 4),
    )

    assert week.week_start_date.weekday() == 0
    assert (week.week_end_date - week.week_start_date).days == 6


def test_session_plan_item_model_contract():
    table = SessionPlanItem.__table__

    assert table.name == "session_plan_items"

    assert table.c.session_plan_week_id.nullable is False
    assert table.c.class_division_id.nullable is False
    assert table.c.planned_date.nullable is False
    assert table.c.sequence_no.nullable is False

    assert table.c.planned_start_time.nullable is True
    assert table.c.planned_end_time.nullable is True

    unique_constraints = get_unique_constraints(SessionPlanItem)

    assert unique_constraints["uq_session_plan_item_week_sequence"] == (
        "session_plan_week_id",
        "sequence_no",
    )

    check_constraints = get_check_constraint_names(SessionPlanItem)

    assert "ck_session_plan_item_sequence_positive" in check_constraints
    assert "ck_session_plan_item_planned_time_range" in check_constraints
    assert "ck_session_plan_item_data_origin" in check_constraints


def test_session_plan_item_relationships():
    assert SessionPlanItem.session_plan_week.property.back_populates == (
        "items"
    )

    assert SessionPlanItem.content.property.back_populates == (
        "session_plan_item"
    )

    assert SessionPlanItem.teaching_session.property.back_populates == (
        "session_plan_item"
    )

    assert SessionPlanItem.content.property.uselist is False
    assert SessionPlanItem.teaching_session.property.uselist is False

    content_cascade = SessionPlanItem.content.property.cascade

    assert "save-update" in content_cascade
    assert "delete" in content_cascade
    assert "delete-orphan" in content_cascade

    teaching_session_cascade = SessionPlanItem.teaching_session.property.cascade

    assert "delete" not in teaching_session_cascade
    assert "delete-orphan" not in teaching_session_cascade


def test_session_plan_item_time_values_are_representable():
    item = SessionPlanItem(
        session_plan_week_id="00000000-0000-0000-0000-000000000001",
        class_division_id="00000000-0000-0000-0000-000000000002",
        planned_date=date(2026, 9, 29),
        planned_start_time=time(9, 0),
        planned_end_time=time(10, 0),
        sequence_no=1,
    )

    assert item.planned_start_time == time(9, 0)
    assert item.planned_end_time == time(10, 0)
    assert item.sequence_no == 1


def test_session_plan_content_model_contract():
    table = SessionPlanContent.__table__

    assert table.name == "session_plan_contents"

    assert table.c.session_plan_item_id.nullable is False
    assert table.c.content.nullable is False

    assert any(
        index.unique
        and tuple(column.name for column in index.columns)
        == ("session_plan_item_id",)
        for index in table.indexes
    )


def test_teaching_session_plan_item_is_unique():
    table = TeachingSession.__table__

    assert table.c.session_plan_item_id.nullable is True

    assert any(
        index.unique
        and tuple(column.name for column in index.columns)
        == ("session_plan_item_id",)
        for index in table.indexes
    )


def test_session_plan_content_is_one_to_zero_or_one():
    assert SessionPlanItem.content.property.uselist is False
    assert SessionPlanContent.session_plan_item.property.uselist is False


def test_session_plan_content_relationship_is_bidirectional():
    assert SessionPlanContent.session_plan_item.property.back_populates == (
        "content"
    )

    assert SessionPlanItem.content.property.back_populates == (
        "session_plan_item"
    )


def test_session_plan_item_can_exist_without_content():
    item = SessionPlanItem(
        session_plan_week_id="00000000-0000-0000-0000-000000000001",
        class_division_id="00000000-0000-0000-0000-000000000002",
        planned_date=date(2026, 9, 29),
        sequence_no=1,
    )

    assert item.content is None


def test_session_plan_item_can_have_exactly_one_content_object():
    item = SessionPlanItem(
        session_plan_week_id="00000000-0000-0000-0000-000000000001",
        class_division_id="00000000-0000-0000-0000-000000000002",
        planned_date=date(2026, 9, 29),
        sequence_no=1,
    )

    content = SessionPlanContent(
        content="Fractions and equivalent fractions",
    )

    item.content = content

    assert item.content is content
    assert content.session_plan_item is item


def test_teaching_session_plan_item_is_nullable():
    table = TeachingSession.__table__

    assert table.c.session_plan_item_id.nullable is True


def test_teaching_session_plan_item_relationship_is_one_to_zero_or_one():
    assert TeachingSession.session_plan_item.property.uselist is False
    assert SessionPlanItem.teaching_session.property.uselist is False

    assert TeachingSession.session_plan_item.property.back_populates == (
        "teaching_session"
    )

    assert SessionPlanItem.teaching_session.property.back_populates == (
        "session_plan_item"
    )


def test_teaching_session_can_exist_without_plan_item():
    session = TeachingSession(
        class_division_id="00000000-0000-0000-0000-000000000001",
        para_teacher_id="00000000-0000-0000-0000-000000000002",
        session_date=date(2026, 9, 29),
    )

    assert session.session_plan_item_id is None
    assert session.session_plan_item is None


def test_planned_date_is_not_enforced_by_session_plan_item_model():
    planned_date = date(2026, 10, 5)

    item = SessionPlanItem(
        session_plan_week_id="00000000-0000-0000-0000-000000000001",
        class_division_id="00000000-0000-0000-0000-000000000002",
        planned_date=planned_date,
        sequence_no=1,
    )

    assert item.planned_date == planned_date

