"""add main rule execution mode and rule ordering

Revision ID: 20260409_0023
Revises: 20260408_0022
Create Date: 2026-04-09 11:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260409_0023"
down_revision = "20260408_0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("rules", sa.Column("execution_order", sa.Integer(), nullable=True))
    op.add_column("rules_history", sa.Column("execution_order", sa.Integer(), nullable=True))

    op.execute(
        """
        WITH ordered_rules AS (
            SELECT
                r_id,
                ROW_NUMBER() OVER (
                    PARTITION BY o_id
                    ORDER BY created_at ASC NULLS LAST, r_id ASC
                ) AS next_execution_order
            FROM rules
        )
        UPDATE rules
        SET execution_order = ordered_rules.next_execution_order
        FROM ordered_rules
        WHERE rules.r_id = ordered_rules.r_id
        """
    )
    op.execute(
        """
        UPDATE rules_history
        SET execution_order = rules.execution_order
        FROM rules
        WHERE rules_history.r_id = rules.r_id
        """
    )

    op.alter_column("rules", "execution_order", nullable=False)
    op.alter_column("rules_history", "execution_order", nullable=False)


def downgrade() -> None:
    op.execute("DELETE FROM runtime_settings WHERE key = 'main_rule_execution_mode'")
    op.drop_column("rules_history", "execution_order")
    op.drop_column("rules", "execution_order")
