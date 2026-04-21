"""Add AI rule authoring history audit table.

Revision ID: 20260420_0024
Revises: 20260409_0023
Create Date: 2026-04-20 12:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260420_0024"
down_revision = "20260409_0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_rule_authoring_history",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("generation_id", sa.String(length=36), nullable=False),
        sa.Column("r_id", sa.Integer(), nullable=True),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("evaluation_lane", sa.String(length=32), nullable=False, server_default="main"),
        sa.Column("provider", sa.String(length=128), nullable=False),
        sa.Column("model", sa.String(length=255), nullable=False),
        sa.Column("prompt_excerpt", sa.String(length=255), nullable=True),
        sa.Column("prompt_hash", sa.String(length=64), nullable=False),
        sa.Column("validation_status", sa.String(length=32), nullable=False),
        sa.Column("repair_attempted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("applyable", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("o_id", sa.Integer(), nullable=False),
        sa.Column("changed", sa.DateTime(), nullable=False),
        sa.Column("changed_by", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_rule_authoring_history_o_id_changed",
        "ai_rule_authoring_history",
        ["o_id", "changed"],
        unique=False,
    )
    op.create_index(
        "ix_ai_rule_authoring_history_generation_id",
        "ai_rule_authoring_history",
        ["generation_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_rule_authoring_history_r_id",
        "ai_rule_authoring_history",
        ["r_id"],
        unique=False,
    )
    op.alter_column("ai_rule_authoring_history", "evaluation_lane", server_default=None)
    op.alter_column("ai_rule_authoring_history", "repair_attempted", server_default=None)
    op.alter_column("ai_rule_authoring_history", "applyable", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_ai_rule_authoring_history_r_id", table_name="ai_rule_authoring_history")
    op.drop_index("ix_ai_rule_authoring_history_generation_id", table_name="ai_rule_authoring_history")
    op.drop_index("ix_ai_rule_authoring_history_o_id_changed", table_name="ai_rule_authoring_history")
    op.drop_table("ai_rule_authoring_history")
