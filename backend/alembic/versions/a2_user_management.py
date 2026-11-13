"""Add account categories, user-code counters, and audit events.

Revision ID: a2_user_management
Revises: 9b0039300e28
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "a2_user_management"
down_revision: Union[str, Sequence[str], None] = "9b0039300e28"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


ROLE_CODES = (
    "PLATFORM_OWNER",
    "SYSTEM_ADMIN",
    "DATA_MANAGER",
    "MANAGEMENT",
    "STEM_COORDINATOR",
    "PARA_TEACHER",
)


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("account_category", sa.String(length=30), nullable=True),
    )


    op.execute(
        sa.text(
            """
            UPDATE users
            SET account_category = CASE
                -- Existing canonical user-code prefixes
                WHEN user_code ~ '^PO[0-9]+$'
                    THEN 'PLATFORM_OWNER'
                WHEN user_code ~ '^SA[0-9]+$'
                    THEN 'SYSTEM_ADMIN'
                WHEN user_code ~ '^DM[0-9]+$'
                    THEN 'DATA_MANAGER'
                WHEN user_code ~ '^MG[0-9]+$'
                    THEN 'MANAGEMENT'
                WHEN user_code ~ '^SC[0-9]+$'
                    THEN 'STEM_COORDINATOR'
                WHEN user_code ~ '^PT[0-9]+$'
                    THEN 'PARA_TEACHER'

                -- Existing assessment API accounts
                WHEN user_code = 'AA-M-57876db19e'
                    THEN 'SYSTEM_ADMIN'
                WHEN user_code = 'AA-V-57876db19e'
                    THEN 'MANAGEMENT'

                -- Existing legacy para-teacher accounts
                WHEN user_code ~ '^PT-[0-9a-f]{8}$'
                    THEN 'PARA_TEACHER'

                -- Existing QA account
                WHEN user_code = 'PV-QA-PARATEACHER-01'
                    THEN 'PARA_TEACHER'

                ELSE NULL
            END
            """
        )
    )

    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM users WHERE account_category IS NULL
                ) THEN
                    RAISE EXCEPTION
                        'A2 migration: unresolved account categories remain';
                END IF;
            END $$;
            """
        )
    )

    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1
                    FROM users
                    WHERE user_code !~ '^(PO|SA|DM|MG|SC|PT)[0-9]+$'
                      AND user_code !~ '^PT-[0-9a-f]{8}$'
                      AND user_code !~ '^AA-[MV]-[0-9a-f]{10}$'
                      AND user_code <> 'PV-QA-PARATEACHER-01'
                ) THEN
                    RAISE EXCEPTION
                        'A2 migration: unrecognized user_code format';
                END IF;
            END $$;
            """
        )
    )

    op.create_check_constraint(
        "ck_user_account_category",
        "users",
        "account_category IN ('PLATFORM_OWNER', 'SYSTEM_ADMIN', 'DATA_MANAGER', "
        "'MANAGEMENT', 'STEM_COORDINATOR', 'PARA_TEACHER')",
    )
    op.create_check_constraint(
        "ck_user_status",
        "users",
        "status IN ('ACTIVE', 'DISABLED')",
    )
    op.alter_column(
        "users",
        "account_category",
        existing_type=sa.String(length=30),
        nullable=False,
    )

    op.create_table(
        "user_code_counters",
        sa.Column("prefix", sa.String(length=2), primary_key=True),
        sa.Column("next_number", sa.BigInteger(), nullable=False),
        sa.CheckConstraint("next_number > 0", name="ck_user_code_counter_positive"),
    )
    op.execute(
        sa.text(
            """
            INSERT INTO user_code_counters (prefix, next_number)
            SELECT prefix, COALESCE(MAX(number_value), 0) + 1
            FROM (
                SELECT
                    SUBSTRING(user_code FROM '^(PO|SA|DM|MG|SC|PT)') AS prefix,
                    CAST(
                        SUBSTRING(
                            user_code FROM '^[A-Z]{2}([0-9]+)$'
                        ) AS BIGINT
                    ) AS number_value
                FROM users
            ) existing_codes
            WHERE prefix IS NOT NULL AND number_value IS NOT NULL
            GROUP BY prefix
            """
        )
    )
    op.execute(
        sa.text(
            """
            INSERT INTO user_code_counters (prefix, next_number)
            VALUES
                ('PO', 1), ('SA', 1), ('DM', 1),
                ('MG', 1), ('SC', 1), ('PT', 1)
            ON CONFLICT (prefix) DO NOTHING
            """
        )
    )

    op.create_table(
        "audit_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("target_type", sa.String(length=50), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=True),
        sa.Column("outcome", sa.String(length=10), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "outcome IN ('SUCCESS', 'FAILURE')",
            name="ck_audit_event_outcome",
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_events_actor_created", "audit_events", ["actor_id", "created_at"])
    op.create_index("ix_audit_events_target_created", "audit_events", ["target_type", "target_id", "created_at"])
    op.create_index("ix_audit_events_action_created", "audit_events", ["action", "created_at"])
    op.create_index("ix_audit_events_created_at", "audit_events", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_audit_events_created_at", table_name="audit_events")
    op.drop_index("ix_audit_events_action_created", table_name="audit_events")
    op.drop_index("ix_audit_events_target_created", table_name="audit_events")
    op.drop_index("ix_audit_events_actor_created", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_table("user_code_counters")
    op.drop_constraint("ck_user_status", "users", type_="check")
    op.drop_constraint("ck_user_account_category", "users", type_="check")
    op.drop_column("users", "account_category")
