"""expand engagement score range

Revision ID: ee7745fc
Revises: 10022223c091
Create Date: 2026-09-23
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "ee7745fc"
down_revision: Union[str, Sequence[str], None] = "10022223c091"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Expand engagement score range from 1-5 to 1-10."""

    op.drop_constraint(
        "ck_session_engagement_score",
        "session_engagement",
        type_="check",
    )

    op.create_check_constraint(
        "ck_session_engagement_score",
        "session_engagement",
        "score >= 1 AND score <= 10",
    )


def downgrade() -> None:
    """Restore engagement score range from 1-10 to 1-5."""

    op.drop_constraint(
        "ck_session_engagement_score",
        "session_engagement",
        type_="check",
    )

    op.create_check_constraint(
        "ck_session_engagement_score",
        "session_engagement",
        "score >= 1 AND score <= 5",
    )