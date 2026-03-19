"""Scope runtime settings to organisations.

Revision ID: 20260318_0012
Revises: 20260317_0011
Create Date: 2026-03-18 10:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260318_0012"
down_revision = "20260317_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("runtime_settings")
    op.create_table(
        "runtime_settings",
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column("o_id", sa.Integer(), nullable=False),
        sa.Column("value_type", sa.String(length=20), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["o_id"], ["organisation.o_id"]),
        sa.PrimaryKeyConstraint("key", "o_id"),
    )


def downgrade() -> None:
    op.drop_table("runtime_settings")
    op.create_table(
        "runtime_settings",
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column("value_type", sa.String(length=20), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )
