"""add paused rule status

Revision ID: 20260408_0022
Revises: 20260407_0021
Create Date: 2026-04-08 10:00:00.000000
"""

from __future__ import annotations

from alembic import op


# revision identifiers, used by Alembic.
revision = "20260408_0022"
down_revision = "20260407_0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE rule_status_enum ADD VALUE IF NOT EXISTS 'paused'")


def downgrade() -> None:
    op.execute("UPDATE rules SET status = 'draft' WHERE status = 'paused'")
    op.execute("UPDATE rules_history SET status = 'draft' WHERE status = 'paused'")
    op.execute("UPDATE rules_history SET to_status = 'draft' WHERE to_status = 'paused'")
    op.execute("ALTER TYPE rule_status_enum RENAME TO rule_status_enum_old")
    op.execute("CREATE TYPE rule_status_enum AS ENUM ('draft', 'active', 'archived')")
    op.execute(
        """
        ALTER TABLE rules
        ALTER COLUMN status TYPE rule_status_enum
        USING status::text::rule_status_enum
        """
    )
    op.execute(
        """
        ALTER TABLE rules_history
        ALTER COLUMN status TYPE rule_status_enum
        USING status::text::rule_status_enum
        """
    )
    op.execute(
        """
        ALTER TABLE rules_history
        ALTER COLUMN to_status TYPE rule_status_enum
        USING CASE
            WHEN to_status IS NULL THEN NULL
            ELSE to_status::text::rule_status_enum
        END
        """
    )
    op.execute("DROP TYPE rule_status_enum_old")
