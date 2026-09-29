"""add session planning

Revision ID: 70924e9abbe5
Revises: 7964c4b6cabb
Create Date: 2026-09-29
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "70924e9abbe5"
down_revision: Union[str, Sequence[str], None] = "7964c4b6cabb"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "session_plan_weeks",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "para_teacher_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "week_start_date",
            sa.Date(),
            nullable=False,
        ),
        sa.Column(
            "week_end_date",
            sa.Date(),
            nullable=False,
        ),
        sa.Column(
            "data_origin",
            sa.String(length=20),
            server_default="PRODUCTION",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["para_teacher_id"],
            ["users.id"],
            name="fk_session_plan_week_para_teacher",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "para_teacher_id",
            "week_start_date",
            name="uq_session_plan_week_teacher_start",
        ),
        sa.CheckConstraint(
            "EXTRACT(ISODOW FROM week_start_date) = 1",
            name="ck_session_plan_week_monday_start",
        ),
        sa.CheckConstraint(
            "week_end_date = week_start_date + 6",
            name="ck_session_plan_week_seven_days",
        ),
        sa.CheckConstraint(
            "data_origin IN ('PRODUCTION', 'DEMO', 'TEST')",
            name="ck_session_plan_week_data_origin",
        ),
    )

    op.create_index(
        "ix_session_plan_weeks_para_teacher_id",
        "session_plan_weeks",
        ["para_teacher_id"],
    )

    op.create_index(
        "ix_session_plan_weeks_week_start_date",
        "session_plan_weeks",
        ["week_start_date"],
    )

    op.create_table(
        "session_plan_items",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "session_plan_week_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "class_division_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "planned_date",
            sa.Date(),
            nullable=False,
        ),
        sa.Column(
            "planned_start_time",
            sa.Time(),
            nullable=True,
        ),
        sa.Column(
            "planned_end_time",
            sa.Time(),
            nullable=True,
        ),
        sa.Column(
            "sequence_no",
            sa.SmallInteger(),
            nullable=False,
        ),
        sa.Column(
            "data_origin",
            sa.String(length=20),
            server_default="PRODUCTION",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["session_plan_week_id"],
            ["session_plan_weeks.id"],
            name="fk_session_plan_item_week",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["class_division_id"],
            ["class_divisions.id"],
            name="fk_session_plan_item_class_division",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "session_plan_week_id",
            "sequence_no",
            name="uq_session_plan_item_week_sequence",
        ),
        sa.CheckConstraint(
            "sequence_no > 0",
            name="ck_session_plan_item_sequence_positive",
        ),
        sa.CheckConstraint(
            "(planned_start_time IS NULL "
            "AND planned_end_time IS NULL) "
            "OR "
            "(planned_start_time IS NOT NULL "
            "AND planned_end_time IS NOT NULL "
            "AND planned_end_time > planned_start_time)",
            name="ck_session_plan_item_planned_time_range",
        ),
        sa.CheckConstraint(
            "data_origin IN ('PRODUCTION', 'DEMO', 'TEST')",
            name="ck_session_plan_item_data_origin",
        ),
    )

    op.create_index(
        "ix_session_plan_items_session_plan_week_id",
        "session_plan_items",
        ["session_plan_week_id"],
    )

    op.create_index(
        "ix_session_plan_items_class_division_id",
        "session_plan_items",
        ["class_division_id"],
    )

    op.create_index(
        "ix_session_plan_items_planned_date",
        "session_plan_items",
        ["planned_date"],
    )

    op.create_table(
        "session_plan_contents",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "session_plan_item_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "content",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "data_origin",
            sa.String(length=20),
            server_default="PRODUCTION",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["session_plan_item_id"],
            ["session_plan_items.id"],
            name="fk_session_plan_content_item",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "session_plan_item_id",
            name="uq_session_plan_content_item",
        ),
        sa.CheckConstraint(
            "data_origin IN ('PRODUCTION', 'DEMO', 'TEST')",
            name="ck_session_plan_content_data_origin",
        ),
    )

    op.create_index(
        "ix_session_plan_contents_session_plan_item_id",
        "session_plan_contents",
        ["session_plan_item_id"],
    )

    op.add_column(
        "teaching_sessions",
        sa.Column(
            "session_plan_item_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )

    op.create_index(
        "ix_teaching_sessions_session_plan_item_id",
        "teaching_sessions",
        ["session_plan_item_id"],
        unique=True,
    )

    op.create_foreign_key(
        "fk_teaching_session_session_plan_item",
        "teaching_sessions",
        "session_plan_items",
        ["session_plan_item_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_teaching_session_session_plan_item",
        "teaching_sessions",
        type_="foreignkey",
    )

    op.drop_index(
        "ix_teaching_sessions_session_plan_item_id",
        table_name="teaching_sessions",
    )

    op.drop_column(
        "teaching_sessions",
        "session_plan_item_id",
    )

    op.drop_index(
        "ix_session_plan_contents_session_plan_item_id",
        table_name="session_plan_contents",
    )

    op.drop_table("session_plan_contents")

    op.drop_index(
        "ix_session_plan_items_planned_date",
        table_name="session_plan_items",
    )

    op.drop_index(
        "ix_session_plan_items_class_division_id",
        table_name="session_plan_items",
    )

    op.drop_index(
        "ix_session_plan_items_session_plan_week_id",
        table_name="session_plan_items",
    )

    op.drop_table("session_plan_items")

    op.drop_index(
        "ix_session_plan_weeks_week_start_date",
        table_name="session_plan_weeks",
    )

    op.drop_index(
        "ix_session_plan_weeks_para_teacher_id",
        table_name="session_plan_weeks",
    )

    op.drop_table("session_plan_weeks")