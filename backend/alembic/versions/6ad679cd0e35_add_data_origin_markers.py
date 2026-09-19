"""add data origin markers

Revision ID: 6ad679cd0e35
Revises: 8f8f0d6214df
Create Date: 2026-09-19 07:48:07.946817

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6ad679cd0e35'
down_revision: Union[str, Sequence[str], None] = '8f8f0d6214df'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "class_divisions",
        sa.Column(
            "data_origin",
            sa.String(length=20),
            server_default="PRODUCTION",
            nullable=False,
        ),
    )
    op.add_column(
        "schools",
        sa.Column(
            "data_origin",
            sa.String(length=20),
            server_default="PRODUCTION",
            nullable=False,
        ),
    )
    op.add_column(
        "students",
        sa.Column(
            "data_origin",
            sa.String(length=20),
            server_default="PRODUCTION",
            nullable=False,
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "data_origin",
            sa.String(length=20),
            server_default="PRODUCTION",
            nullable=False,
        ),
    )

    op.create_check_constraint(
        "ck_class_division_data_origin",
        "class_divisions",
        "data_origin IN ('PRODUCTION', 'DEMO', 'TEST')",
    )

    op.create_check_constraint(
        "ck_school_data_origin",
        "schools",
        "data_origin IN ('PRODUCTION', 'DEMO', 'TEST')",
    )

    op.create_check_constraint(
        "ck_student_data_origin",
        "students",
        "data_origin IN ('PRODUCTION', 'DEMO', 'TEST')",
    )

    op.create_check_constraint(
        "ck_user_data_origin",
        "users",
        "data_origin IN ('PRODUCTION', 'DEMO', 'TEST')",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        "ck_user_data_origin",
        "users",
        type_="check",
    )
    op.drop_constraint(
        "ck_student_data_origin",
        "students",
        type_="check",
    )
    op.drop_constraint(
        "ck_school_data_origin",
        "schools",
        type_="check",
    )
    op.drop_constraint(
        "ck_class_division_data_origin",
        "class_divisions",
        type_="check",
    )

    op.drop_column("users", "data_origin")
    op.drop_column("students", "data_origin")
    op.drop_column("schools", "data_origin")
    op.drop_column("class_divisions", "data_origin")
    