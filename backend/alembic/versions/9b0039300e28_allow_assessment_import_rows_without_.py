"""Allow assessment import rows without student names.

Revision ID: 9b0039300e28
Revises: 24e72e224c10
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "9b0039300e28"
down_revision: Union[str, Sequence[str], None] = "24e72e224c10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Allow assessment import rows without student names."""
    op.alter_column(
        "assessment_import_rows",
        "source_student_name",
        existing_type=sa.String(length=150),
        nullable=True,
    )


def downgrade() -> None:
    """Restore the original non-null constraint."""
    op.alter_column(
        "assessment_import_rows",
        "source_student_name",
        existing_type=sa.String(length=150),
        nullable=False,
    )