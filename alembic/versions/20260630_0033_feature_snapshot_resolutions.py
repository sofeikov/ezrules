"""Add feature snapshot resolution audit storage.

Revision ID: 20260630_0033
Revises: 20260625_0032
Create Date: 2026-06-30
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260630_0033"
down_revision: str | None = "20260625_0032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "feature_snapshot_resolutions",
        sa.Column("fsr_id", sa.Integer(), nullable=False),
        sa.Column("o_id", sa.Integer(), nullable=False),
        sa.Column("ed_id", sa.Integer(), nullable=True),
        sa.Column("backtest_task_id", sa.String(), nullable=True),
        sa.Column("backtest_record_index", sa.Integer(), nullable=True),
        sa.Column("fd_id", sa.Integer(), nullable=True),
        sa.Column("stat_path", sa.String(length=255), nullable=False),
        sa.Column("feature_kind", sa.String(length=32), nullable=True),
        sa.Column("feature_version", sa.Integer(), nullable=True),
        sa.Column("as_of", sa.DateTime(), nullable=False),
        sa.Column("window_start", sa.DateTime(), nullable=False),
        sa.Column("matched_event_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("entity_value_hash", sa.String(length=64), nullable=True),
        sa.Column("resolution_status", sa.String(length=32), nullable=False, server_default="resolved"),
        sa.Column("warning", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["ed_id"], ["evaluation_decisions.ed_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["fd_id"], ["feature_definitions.fd_id"]),
        sa.ForeignKeyConstraint(["o_id"], ["organisation.o_id"]),
        sa.PrimaryKeyConstraint("fsr_id"),
        sa.UniqueConstraint("fsr_id"),
    )
    op.create_index(
        "ix_feature_snapshot_resolutions_o_id_ed_id",
        "feature_snapshot_resolutions",
        ["o_id", "ed_id"],
    )
    op.create_index(
        "ix_feature_snapshot_resolutions_o_id_backtest_task",
        "feature_snapshot_resolutions",
        ["o_id", "backtest_task_id"],
    )
    op.create_index(
        "ix_feature_snapshot_resolutions_o_id_stat_as_of",
        "feature_snapshot_resolutions",
        ["o_id", "stat_path", "as_of"],
    )
    op.alter_column("feature_snapshot_resolutions", "matched_event_count", server_default=None)
    op.alter_column("feature_snapshot_resolutions", "resolution_status", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_feature_snapshot_resolutions_o_id_stat_as_of", table_name="feature_snapshot_resolutions")
    op.drop_index("ix_feature_snapshot_resolutions_o_id_backtest_task", table_name="feature_snapshot_resolutions")
    op.drop_index("ix_feature_snapshot_resolutions_o_id_ed_id", table_name="feature_snapshot_resolutions")
    op.drop_table("feature_snapshot_resolutions")
