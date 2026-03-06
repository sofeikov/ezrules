"""Add rule quality reports table.

Revision ID: 20260306_0005
Revises: 20260306_0004
Create Date: 2026-03-06 17:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260306_0005"
down_revision = "20260306_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "rule_quality_reports",
        sa.Column("rqr_id", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.String(length=50), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("min_support", sa.Integer(), nullable=False),
        sa.Column("lookback_days", sa.Integer(), nullable=False),
        sa.Column("freeze_at", sa.DateTime(), nullable=False),
        sa.Column("max_tl_id", sa.Integer(), nullable=False),
        sa.Column("requested_by", sa.String(length=255), nullable=True),
        sa.Column("error", sa.String(), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("o_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["o_id"], ["organisation.o_id"]),
        sa.PrimaryKeyConstraint("rqr_id"),
        sa.UniqueConstraint("rqr_id"),
    )

    op.create_index("ix_rule_quality_reports_task_id", "rule_quality_reports", ["task_id"], unique=False)
    op.create_index("ix_rule_quality_reports_status", "rule_quality_reports", ["status"], unique=False)
    op.create_index(
        "ix_rule_quality_reports_lookup",
        "rule_quality_reports",
        ["o_id", "min_support", "lookback_days", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_rule_quality_reports_lookup", table_name="rule_quality_reports")
    op.drop_index("ix_rule_quality_reports_status", table_name="rule_quality_reports")
    op.drop_index("ix_rule_quality_reports_task_id", table_name="rule_quality_reports")
    op.drop_table("rule_quality_reports")
