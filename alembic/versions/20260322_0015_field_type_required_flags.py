"""Add required flags to field type config and history.

Revision ID: 20260322_0015
Revises: 20260318_0014
Create Date: 2026-03-22 12:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = "20260322_0015"
down_revision = "20260318_0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("field_type_config") as batch_op:
        batch_op.add_column(sa.Column("required", sa.Boolean(), nullable=False, server_default=sa.false()))

    with op.batch_alter_table("field_type_history") as batch_op:
        batch_op.add_column(sa.Column("required", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    with op.batch_alter_table("field_type_history") as batch_op:
        batch_op.drop_column("required")

    with op.batch_alter_table("field_type_config") as batch_op:
        batch_op.drop_column("required")
