"""Tenant-scope roles, labels, and remaining audit history.

Revision ID: 20260318_0013
Revises: 20260318_0012
Create Date: 2026-03-18 16:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260318_0013"
down_revision = "20260318_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("role") as batch_op:
        batch_op.add_column(sa.Column("o_id", sa.Integer(), nullable=False))
        batch_op.create_foreign_key("fk_role_o_id_organisation", "organisation", ["o_id"], ["o_id"])
        batch_op.create_index("ix_role_o_id", ["o_id"], unique=False)
        batch_op.drop_constraint("role_name_key", type_="unique")
        batch_op.create_unique_constraint("uq_role_org_name", ["o_id", "name"])

    with op.batch_alter_table("event_labels") as batch_op:
        batch_op.add_column(sa.Column("o_id", sa.Integer(), nullable=False))
        batch_op.create_foreign_key("fk_event_labels_o_id_organisation", "organisation", ["o_id"], ["o_id"])
        batch_op.create_index("ix_event_labels_o_id", ["o_id"], unique=False)
        batch_op.drop_constraint("event_labels_label_key", type_="unique")
        batch_op.create_unique_constraint("uq_event_labels_org_label", ["o_id", "label"])

    with op.batch_alter_table("label_history") as batch_op:
        batch_op.add_column(sa.Column("o_id", sa.Integer(), nullable=False))
        batch_op.create_index("ix_label_history_o_id", ["o_id"], unique=False)

    with op.batch_alter_table("user_account_history") as batch_op:
        batch_op.add_column(sa.Column("o_id", sa.Integer(), nullable=False))
        batch_op.create_index("ix_user_account_history_o_id", ["o_id"], unique=False)

    with op.batch_alter_table("role_permission_history") as batch_op:
        batch_op.add_column(sa.Column("o_id", sa.Integer(), nullable=False))
        batch_op.create_index("ix_role_permission_history_o_id", ["o_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("role_permission_history") as batch_op:
        batch_op.drop_index("ix_role_permission_history_o_id")
        batch_op.drop_column("o_id")

    with op.batch_alter_table("user_account_history") as batch_op:
        batch_op.drop_index("ix_user_account_history_o_id")
        batch_op.drop_column("o_id")

    with op.batch_alter_table("label_history") as batch_op:
        batch_op.drop_index("ix_label_history_o_id")
        batch_op.drop_column("o_id")

    with op.batch_alter_table("event_labels") as batch_op:
        batch_op.drop_constraint("uq_event_labels_org_label", type_="unique")
        batch_op.create_unique_constraint("event_labels_label_key", ["label"])
        batch_op.drop_index("ix_event_labels_o_id")
        batch_op.drop_constraint("fk_event_labels_o_id_organisation", type_="foreignkey")
        batch_op.drop_column("o_id")

    with op.batch_alter_table("role") as batch_op:
        batch_op.drop_constraint("uq_role_org_name", type_="unique")
        batch_op.create_unique_constraint("role_name_key", ["name"])
        batch_op.drop_index("ix_role_o_id")
        batch_op.drop_constraint("fk_role_o_id_organisation", type_="foreignkey")
        batch_op.drop_column("o_id")
