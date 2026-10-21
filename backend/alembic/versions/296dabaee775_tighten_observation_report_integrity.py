"""tighten observation report integrity

Revision ID: 296dabaee775
Revises: c1d834700602
Create Date: 2026-10-15 05:40:39.878077

"""
from typing import Sequence, Union

from alembic import op

revision: str = "296dabaee775"
down_revision: Union[str, Sequence[str], None] = "c1d834700602"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Require exactly one report reference per correction history row.
    op.create_check_constraint(
        "ck_observation_correction_one_report",
        "observation_report_corrections",
        """
        (observation_report_id IS NOT NULL AND inspection_report_id IS NULL)
        OR
        (observation_report_id IS NULL AND inspection_report_id IS NOT NULL)
        """,
    )

    # A pending report has no payload. A completed report must have
    # exactly one valid payload matching its mode.
    op.drop_constraint(
        "ck_classroom_report_payload",
        "classroom_observation_reports",
        type_="check",
    )
    op.create_check_constraint(
        "ck_classroom_report_payload",
        "classroom_observation_reports",
        """
        (status = 'PENDING'
            AND mode IS NULL
            AND storage_key IS NULL
            AND external_url IS NULL)
        OR
        (status = 'COMPLETE' AND mode = 'UPLOAD'
            AND storage_key IS NOT NULL
            AND external_url IS NULL)
        OR
        (status = 'COMPLETE' AND mode = 'LINK'
            AND storage_key IS NULL
            AND external_url IS NOT NULL)
        """,
    )

    op.drop_constraint(
        "ck_stem_report_payload",
        "stem_inspection_reports",
        type_="check",
    )
    op.create_check_constraint(
        "ck_stem_report_payload",
        "stem_inspection_reports",
        """
        (status = 'PENDING'
            AND mode IS NULL
            AND storage_key IS NULL
            AND external_url IS NULL)
        OR
        (status = 'COMPLETE' AND mode = 'UPLOAD'
            AND storage_key IS NOT NULL
            AND external_url IS NULL)
        OR
        (status = 'COMPLETE' AND mode = 'LINK'
            AND storage_key IS NULL
            AND external_url IS NOT NULL)
        """,
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_stem_report_payload",
        "stem_inspection_reports",
        type_="check",
    )
    op.create_check_constraint(
        "ck_stem_report_payload",
        "stem_inspection_reports",
        """
        (mode = 'UPLOAD' AND storage_key IS NOT NULL AND external_url IS NULL)
        OR
        (mode = 'LINK' AND storage_key IS NULL AND external_url IS NOT NULL)
        OR
        (status = 'PENDING' AND mode IS NULL
            AND storage_key IS NULL AND external_url IS NULL)
        """,
    )

    op.drop_constraint(
        "ck_classroom_report_payload",
        "classroom_observation_reports",
        type_="check",
    )
    op.create_check_constraint(
        "ck_classroom_report_payload",
        "classroom_observation_reports",
        """
        (mode = 'UPLOAD' AND storage_key IS NOT NULL AND external_url IS NULL)
        OR
        (mode = 'LINK' AND storage_key IS NULL AND external_url IS NOT NULL)
        OR
        (status = 'PENDING' AND mode IS NULL
            AND storage_key IS NULL AND external_url IS NULL)
        """,
    )

    op.drop_constraint(
        "ck_observation_correction_one_report",
        "observation_report_corrections",
        type_="check",
    )
