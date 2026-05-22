"""Add user-list version records.

Revision ID: 20260522_0030
Revises: 20260506_0029
Create Date: 2026-05-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260522_0030"
down_revision: str | None = "20260506_0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_list_versions",
        sa.Column("o_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["o_id"], ["organisation.o_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("o_id"),
    )


def downgrade() -> None:
    op.drop_table("user_list_versions")
