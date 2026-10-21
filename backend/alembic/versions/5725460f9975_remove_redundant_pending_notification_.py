"""remove redundant pending notification constraint

Revision ID: 5725460f9975
Revises: 296dabaee775
Create Date: 2026-10-16 05:12:40.742426

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5725460f9975'
down_revision: Union[str, Sequence[str], None] = '296dabaee775'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint(
        "uq_pending_notification",
        "pending_report_notifications",
        type_="unique",
    )


def downgrade() -> None:
    op.create_unique_constraint(
        "uq_pending_notification",
        "pending_report_notifications",
        [
            "recipient_id",
            "observation_id",
            "inspection_id",
            "notification_type",
        ],
    )