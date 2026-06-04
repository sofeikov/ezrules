"""Add graph feature storage.

Revision ID: 20260604_0031
Revises: 20260522_0030
Create Date: 2026-06-04
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260604_0031"
down_revision: str | None = "20260522_0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "feature_definitions",
        sa.Column("feature_kind", sa.String(length=32), nullable=False, server_default="aggregate"),
    )
    op.add_column("feature_definitions", sa.Column("graph_config", sa.JSON(), nullable=True))
    op.alter_column("feature_definitions", "feature_kind", server_default=None)

    op.create_table(
        "graph_entity_fields",
        sa.Column("gef_id", sa.Integer(), nullable=False),
        sa.Column("o_id", sa.Integer(), nullable=False),
        sa.Column("field_path", sa.String(length=255), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["o_id"], ["organisation.o_id"]),
        sa.PrimaryKeyConstraint("gef_id"),
        sa.UniqueConstraint("gef_id"),
        sa.UniqueConstraint("o_id", "field_path", name="uq_graph_entity_fields_org_field"),
    )
    op.create_index("ix_graph_entity_fields_o_id_status", "graph_entity_fields", ["o_id", "status"])

    op.create_table(
        "graph_event_entity_links",
        sa.Column("gel_id", sa.Integer(), nullable=False),
        sa.Column("o_id", sa.Integer(), nullable=False),
        sa.Column("ev_id", sa.Integer(), nullable=False),
        sa.Column("transaction_id", sa.String(), nullable=False),
        sa.Column("effective_at", sa.DateTime(), nullable=False),
        sa.Column("field_path", sa.String(length=255), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_value", sa.String(length=1024), nullable=True),
        sa.Column("entity_value_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["ev_id"], ["event_versions.ev_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["o_id"], ["organisation.o_id"]),
        sa.PrimaryKeyConstraint("gel_id"),
        sa.UniqueConstraint("gel_id"),
        sa.UniqueConstraint(
            "o_id", "ev_id", "field_path", "entity_value_hash", name="uq_graph_links_event_field_value"
        ),
    )
    op.create_index(
        "ix_graph_links_o_id_entity_effective",
        "graph_event_entity_links",
        ["o_id", "entity_type", "entity_value_hash", "effective_at"],
    )
    op.create_index("ix_graph_links_o_id_ev_id", "graph_event_entity_links", ["o_id", "ev_id"])
    op.create_index("ix_graph_links_o_id_effective_at", "graph_event_entity_links", ["o_id", "effective_at"])


def downgrade() -> None:
    op.drop_index("ix_graph_links_o_id_effective_at", table_name="graph_event_entity_links")
    op.drop_index("ix_graph_links_o_id_ev_id", table_name="graph_event_entity_links")
    op.drop_index("ix_graph_links_o_id_entity_effective", table_name="graph_event_entity_links")
    op.drop_table("graph_event_entity_links")
    op.drop_index("ix_graph_entity_fields_o_id_status", table_name="graph_entity_fields")
    op.drop_table("graph_entity_fields")
    op.drop_column("feature_definitions", "graph_config")
    op.drop_column("feature_definitions", "feature_kind")
