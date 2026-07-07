"""Add structured case resolution workflow fields.

Revision ID: 20260706_0035
Revises: 20260705_0034
Create Date: 2026-07-06
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260706_0035"
down_revision: str | None = "20260705_0034"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("cases", sa.Column("resolution_disposition", sa.String(length=64), nullable=True))
    op.add_column("cases", sa.Column("resolution_action", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("cases", "resolution_action")
    op.drop_column("cases", "resolution_disposition")
