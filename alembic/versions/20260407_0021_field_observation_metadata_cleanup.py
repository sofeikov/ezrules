"""Drop unused field observation count and recency columns.

Revision ID: 20260407_0021
Revises: 20260403_0020
Create Date: 2026-04-07 09:05:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260407_0021"
down_revision = "20260403_0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("field_observation", "last_seen")
    op.drop_column("field_observation", "occurrence_count")


def downgrade() -> None:
    op.add_column(
        "field_observation",
        sa.Column("occurrence_count", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "field_observation",
        sa.Column("last_seen", sa.DateTime(), nullable=True),
    )
    op.alter_column("field_observation", "occurrence_count", server_default=None)
