"""Add organisation ownership to users.

Revision ID: 20260317_0011
Revises: 20260316_0010
Create Date: 2026-03-17 10:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260317_0011"
down_revision = "20260316_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("user") as batch_op:
        batch_op.add_column(sa.Column("o_id", sa.Integer(), nullable=False))
        batch_op.create_foreign_key("fk_user_o_id_organisation", "organisation", ["o_id"], ["o_id"])
        batch_op.create_index("ix_user_o_id", ["o_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("user") as batch_op:
        batch_op.drop_index("ix_user_o_id")
        batch_op.drop_constraint("fk_user_o_id_organisation", type_="foreignkey")
        batch_op.drop_column("o_id")
