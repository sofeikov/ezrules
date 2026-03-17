"""Add details column for label assignment audit entries.

Revision ID: 20260316_0010
Revises: 20260316_0009
Create Date: 2026-03-16 15:30:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260316_0010"
down_revision = "20260316_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("label_history") as batch_op:
        batch_op.add_column(sa.Column("details", sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("label_history") as batch_op:
        batch_op.drop_column("details")
