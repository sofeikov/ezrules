"""Add rule evaluation lane for allowlist short-circuit rules.

Revision ID: 20260403_0020
Revises: 20260331_0019
Create Date: 2026-04-03 12:30:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260403_0020"
down_revision = "20260331_0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "rules",
        sa.Column("evaluation_lane", sa.String(length=32), nullable=False, server_default="main"),
    )
    op.add_column(
        "rules_history",
        sa.Column("evaluation_lane", sa.String(length=32), nullable=False, server_default="main"),
    )
    op.alter_column("rules", "evaluation_lane", server_default=None)
    op.alter_column("rules_history", "evaluation_lane", server_default=None)


def downgrade() -> None:
    op.drop_column("rules_history", "evaluation_lane")
    op.drop_column("rules", "evaluation_lane")
