from sqlalchemy import CheckConstraint, Index

from app.models import PlanningNotification


def test_planning_notification_table_contract():
    table = PlanningNotification.__table__

    assert table.name == "planning_notifications"
    assert table.c.recipient_id.nullable is False
    assert table.c.para_teacher_id.nullable is False
    assert table.c.notification_type.nullable is False
    assert table.c.message.nullable is False
    assert table.c.session_plan_item_id.nullable is True
    assert table.c.week_start_date.nullable is True
    assert table.c.is_read.nullable is False


def test_planning_notification_event_reference_constraint():
    constraints = {
        constraint.name: constraint
        for constraint in PlanningNotification.__table__.constraints
        if isinstance(constraint, CheckConstraint)
    }

    assert "ck_planning_notification_event_reference" in constraints

    sql = str(
        constraints["ck_planning_notification_event_reference"].sqltext
    )

    assert "WEEKLY_PLANNING_NONCOMPLIANCE" in sql
    assert "SESSION_RESCHEDULE_REQUIRED" in sql
    assert "session_plan_item_id IS NULL" in sql
    assert "session_plan_item_id IS NOT NULL" in sql
    assert "week_start_date IS NOT NULL" in sql
    assert "week_start_date IS NULL" in sql


def test_planning_notification_duplicate_protection_indexes():
    indexes = {
        index.name: index
        for index in PlanningNotification.__table__.indexes
        if isinstance(index, Index)
    }

    weekly = indexes["uq_planning_notification_weekly"]
    reschedule = indexes["uq_planning_notification_reschedule"]

    assert weekly.unique is True
    assert reschedule.unique is True

    assert tuple(column.name for column in weekly.columns) == (
        "recipient_id",
        "para_teacher_id",
        "week_start_date",
        "notification_type",
    )

    assert tuple(column.name for column in reschedule.columns) == (
        "recipient_id",
        "session_plan_item_id",
        "notification_type",
    )
