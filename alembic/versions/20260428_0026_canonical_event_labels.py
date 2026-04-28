"""add canonical event-version labels

Revision ID: 20260428_0026
Revises: 20260428_0025
Create Date: 2026-04-28 20:30:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260428_0026"
down_revision = "20260428_0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "event_version_labels",
        sa.Column("evl_id", sa.Integer(), nullable=False),
        sa.Column("o_id", sa.Integer(), nullable=False),
        sa.Column("ev_id", sa.Integer(), nullable=False),
        sa.Column("el_id", sa.Integer(), nullable=False),
        sa.Column("assigned_at", sa.DateTime(), nullable=False),
        sa.Column("assigned_by", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(["ev_id"], ["event_versions.ev_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["o_id"], ["organisation.o_id"]),
        sa.ForeignKeyConstraint(
            ["el_id", "o_id"],
            ["event_labels.el_id", "event_labels.o_id"],
            name="fk_event_version_labels_label_org",
        ),
        sa.PrimaryKeyConstraint("evl_id"),
        sa.UniqueConstraint("evl_id"),
        sa.UniqueConstraint("o_id", "ev_id", name="uq_event_version_labels_org_event_version"),
    )
    op.create_index(
        "ix_event_version_labels_o_id_assigned_at",
        "event_version_labels",
        ["o_id", "assigned_at"],
        unique=False,
    )
    op.create_index(
        "ix_event_version_labels_o_id_el_id",
        "event_version_labels",
        ["o_id", "el_id"],
        unique=False,
    )
    op.alter_column("rule_quality_reports", "max_tl_id", new_column_name="max_decision_id")


def downgrade() -> None:
    op.alter_column("rule_quality_reports", "max_decision_id", new_column_name="max_tl_id")
    op.drop_index("ix_event_version_labels_o_id_el_id", table_name="event_version_labels")
    op.drop_index("ix_event_version_labels_o_id_assigned_at", table_name="event_version_labels")
    op.drop_table("event_version_labels")
