"""Persist backtesting job status, completion metadata, and result payloads.

Revision ID: 20260331_0019
Revises: 20260324_0018
Create Date: 2026-03-31 10:30:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = "20260331_0019"
down_revision = "20260324_0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("rule_backtesting_results", sa.Column("result_metrics", sa.JSON(), nullable=True))
    op.add_column("rule_backtesting_results", sa.Column("completed_at", sa.DateTime(), nullable=True))
    op.add_column("rule_backtesting_results", sa.Column("status", sa.String(length=20), nullable=True))
    op.execute("UPDATE rule_backtesting_results SET status = 'done' WHERE status IS NULL")
    op.alter_column("rule_backtesting_results", "status", nullable=False)


def downgrade() -> None:
    op.drop_column("rule_backtesting_results", "status")
    op.drop_column("rule_backtesting_results", "completed_at")
    op.drop_column("rule_backtesting_results", "result_metrics")
