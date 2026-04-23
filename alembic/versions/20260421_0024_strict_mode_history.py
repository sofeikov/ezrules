"""add strict mode history

Revision ID: 20260421_0024
Revises: 20260409_0023
Create Date: 2026-04-21 12:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260421_0024"
down_revision = "20260420_0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "strict_mode_history",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("details", sa.String(), nullable=True),
        sa.Column("o_id", sa.Integer(), nullable=False),
        sa.Column("changed", sa.DateTime(), nullable=True),
        sa.Column("changed_by", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_strict_mode_history_o_id_changed",
        "strict_mode_history",
        ["o_id", "changed"],
        unique=False,
    )


def downgrade() -> None:
    op.execute("DELETE FROM runtime_settings WHERE key = 'strict_mode_enabled'")
    op.drop_index("ix_strict_mode_history_o_id_changed", table_name="strict_mode_history")
    op.drop_table("strict_mode_history")
