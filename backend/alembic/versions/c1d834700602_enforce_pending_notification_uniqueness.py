"""enforce pending notification uniqueness

Revision ID: c1d834700602
Revises: f00e50964cc7
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "c1d834700602"
down_revision: Union[str, Sequence[str], None] = "f00e50964cc7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "uq_pending_notification_observation",
        "pending_report_notifications",
        ["recipient_id", "observation_id", "notification_type"],
        unique=True,
        postgresql_where=sa.text("observation_id IS NOT NULL"),
    )
    op.create_index(
        "uq_pending_notification_inspection",
        "pending_report_notifications",
        ["recipient_id", "inspection_id", "notification_type"],
        unique=True,
        postgresql_where=sa.text("inspection_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_pending_notification_inspection",
        table_name="pending_report_notifications",
    )
    op.drop_index(
        "uq_pending_notification_observation",
        table_name="pending_report_notifications",
    )