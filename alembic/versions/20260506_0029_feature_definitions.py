"""Add feature definitions.

Revision ID: 20260506_0029
Revises: 20260430_0028
Create Date: 2026-05-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260506_0029"
down_revision: str | None = "20260430_0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "feature_definitions",
        sa.Column("fd_id", sa.Integer(), nullable=False),
        sa.Column("o_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("entity", sa.String(length=64), nullable=False),
        sa.Column("feature_name", sa.String(length=128), nullable=False),
        sa.Column("entity_key", sa.String(length=255), nullable=False),
        sa.Column("aggregation_type", sa.String(length=32), nullable=False),
        sa.Column("source_field", sa.String(length=255), nullable=True),
        sa.Column("window_seconds", sa.Integer(), nullable=False),
        sa.Column("filters", sa.JSON(), nullable=False),
        sa.Column("inclusion_policy", sa.String(length=32), nullable=False, server_default="previous_events"),
        sa.Column("null_handling", sa.String(length=32), nullable=False, server_default="exclude"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("updated_by", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["o_id"], ["organisation.o_id"]),
        sa.PrimaryKeyConstraint("fd_id"),
        sa.UniqueConstraint("fd_id"),
        sa.UniqueConstraint("o_id", "entity", "feature_name", name="uq_feature_definitions_org_path"),
    )
    op.create_index("ix_feature_definitions_o_id_status", "feature_definitions", ["o_id", "status"])
    op.create_table(
        "feature_definition_history",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("fd_id", sa.Integer(), nullable=False),
        sa.Column("entity", sa.String(length=64), nullable=False),
        sa.Column("feature_name", sa.String(length=128), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("details", sa.String(), nullable=True),
        sa.Column("o_id", sa.Integer(), nullable=False),
        sa.Column("changed", sa.DateTime(), nullable=False),
        sa.Column("changed_by", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_feature_definition_history_fd_id", "feature_definition_history", ["fd_id"])
    op.create_index(
        "ix_feature_definition_history_o_id_changed",
        "feature_definition_history",
        ["o_id", "changed"],
    )
    op.create_index(
        "ix_feature_definition_history_o_id_fd_id",
        "feature_definition_history",
        ["o_id", "fd_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_feature_definition_history_o_id_fd_id", table_name="feature_definition_history")
    op.drop_index("ix_feature_definition_history_o_id_changed", table_name="feature_definition_history")
    op.drop_index("ix_feature_definition_history_fd_id", table_name="feature_definition_history")
    op.drop_table("feature_definition_history")
    op.drop_index("ix_feature_definitions_o_id_status", table_name="feature_definitions")
    op.drop_table("feature_definitions")
