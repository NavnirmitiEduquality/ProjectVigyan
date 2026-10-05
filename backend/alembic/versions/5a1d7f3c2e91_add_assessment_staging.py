"""add assessment staging and results

Revision ID: 5a1d7f3c2e91
Revises: 4ccdb42bed02
Create Date: 2026-10-05 05:30:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "5a1d7f3c2e91"
down_revision: Union[str, Sequence[str], None] = "4ccdb42bed02"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "assessments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("academic_year_id", sa.Uuid(), nullable=False),
        sa.Column("school_id", sa.Uuid(), nullable=False),
        sa.Column("assessment_type", sa.String(length=20), nullable=False),
        sa.Column("sequence_no", sa.SmallInteger(), server_default="1", nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("assessment_date", sa.Date(), nullable=True),
        sa.Column("maximum_marks", sa.Numeric(12, 2), nullable=False),
        sa.Column("status", sa.String(length=30), server_default="DRAFT", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("data_origin", sa.String(length=20), server_default="PRODUCTION", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "assessment_type IN ('BASELINE', 'MIDLINE', 'ENDLINE')",
            name="ck_assessment_type",
        ),
        sa.CheckConstraint("sequence_no >= 1", name="ck_assessment_sequence"),
        sa.CheckConstraint(
            "assessment_type = 'MIDLINE' OR sequence_no = 1",
            name="ck_assessment_non_midline_sequence",
        ),
        sa.CheckConstraint("maximum_marks > 0", name="ck_assessment_maximum_marks"),
        sa.CheckConstraint(
            "status IN ('DRAFT', 'READY_FOR_SUBMISSION', 'SUBMITTED')",
            name="ck_assessment_status",
        ),
        sa.CheckConstraint(
            "data_origin IN ('PRODUCTION', 'DEMO', 'TEST')",
            name="ck_assessment_data_origin",
        ),
        sa.ForeignKeyConstraint(["academic_year_id"], ["academic_years.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["school_id"], ["schools.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "academic_year_id",
            "school_id",
            "assessment_type",
            "sequence_no",
            name="uq_assessment_event",
        ),
    )
    op.create_index("ix_assessments_academic_year_id", "assessments", ["academic_year_id"])
    op.create_index("ix_assessments_school_id", "assessments", ["school_id"])

    op.create_table(
        "assessment_imports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("assessment_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="DRAFT", nullable=False),
        sa.Column("total_rows", sa.Integer(), server_default="0", nullable=False),
        sa.Column("warning_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "status IN ('DRAFT', 'VALIDATED', 'SUBMITTED')",
            name="ck_assessment_import_status",
        ),
        sa.CheckConstraint(
            "total_rows >= 0 AND warning_count >= 0 AND error_count >= 0",
            name="ck_assessment_import_counts",
        ),
        sa.ForeignKeyConstraint(["assessment_id"], ["assessments.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_assessment_imports_assessment_id", "assessment_imports", ["assessment_id"])
    op.create_index("ix_assessment_imports_created_by_user_id", "assessment_imports", ["created_by_user_id"])

    op.create_table(
        "assessment_import_rows",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("assessment_import_id", sa.Uuid(), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("student_business_id", sa.String(length=30), nullable=True),
        sa.Column("source_student_name", sa.String(length=150), nullable=False),
        sa.Column("source_class", sa.String(length=20), nullable=True),
        sa.Column("source_division", sa.String(length=20), nullable=True),
        sa.Column("aggregate_marks", sa.Numeric(12, 2), nullable=True),
        sa.Column("student_id", sa.Uuid(), nullable=True),
        sa.Column("class_division_id", sa.Uuid(), nullable=True),
        sa.Column("validation_status", sa.String(length=20), server_default="ERROR", nullable=False),
        sa.Column("validation_message", sa.Text(), nullable=True),
        sa.Column("is_mapped", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("warning_acknowledged", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "validation_status IN ('VALID', 'WARNING', 'ERROR', 'MAPPED')",
            name="ck_assessment_import_row_status",
        ),
        sa.CheckConstraint(
            "aggregate_marks IS NULL OR aggregate_marks >= 0",
            name="ck_assessment_import_row_marks",
        ),
        sa.ForeignKeyConstraint(["assessment_import_id"], ["assessment_imports.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["student_id"], ["students.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["class_division_id"], ["class_divisions.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "assessment_import_id",
            "row_number",
            name="uq_assessment_import_row_number",
        ),
    )
    op.create_index("ix_assessment_import_rows_assessment_import_id", "assessment_import_rows", ["assessment_import_id"])
    op.create_index("ix_assessment_import_rows_student_id", "assessment_import_rows", ["student_id"])
    op.create_index("ix_assessment_import_rows_class_division_id", "assessment_import_rows", ["class_division_id"])

    op.create_table(
        "assessment_results",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("assessment_id", sa.Uuid(), nullable=False),
        sa.Column("student_id", sa.Uuid(), nullable=False),
        sa.Column("student_business_id", sa.String(length=30), nullable=False),
        sa.Column("aggregate_marks", sa.Numeric(12, 2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("aggregate_marks >= 0", name="ck_assessment_result_marks"),
        sa.ForeignKeyConstraint(["assessment_id"], ["assessments.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["student_id"], ["students.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("assessment_id", "student_id", name="uq_assessment_result_student"),
    )
    op.create_index("ix_assessment_results_assessment_id", "assessment_results", ["assessment_id"])
    op.create_index("ix_assessment_results_student_id", "assessment_results", ["student_id"])


def downgrade() -> None:
    op.drop_index("ix_assessment_results_student_id", table_name="assessment_results")
    op.drop_index("ix_assessment_results_assessment_id", table_name="assessment_results")
    op.drop_table("assessment_results")
    op.drop_index("ix_assessment_import_rows_class_division_id", table_name="assessment_import_rows")
    op.drop_index("ix_assessment_import_rows_student_id", table_name="assessment_import_rows")
    op.drop_index("ix_assessment_import_rows_assessment_import_id", table_name="assessment_import_rows")
    op.drop_table("assessment_import_rows")
    op.drop_index("ix_assessment_imports_created_by_user_id", table_name="assessment_imports")
    op.drop_index("ix_assessment_imports_assessment_id", table_name="assessment_imports")
    op.drop_table("assessment_imports")
    op.drop_index("ix_assessments_school_id", table_name="assessments")
    op.drop_index("ix_assessments_academic_year_id", table_name="assessments")
    op.drop_table("assessments")
