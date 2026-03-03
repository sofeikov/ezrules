"""add rule lifecycle and approval fields

Revision ID: 20260303_0002
Revises: 54496a537916
Create Date: 2026-03-03 12:35:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260303_0002"
down_revision = "54496a537916"
branch_labels = None
depends_on = None


rule_status_enum = sa.Enum("draft", "active", "archived", name="rule_status_enum")


def upgrade() -> None:
    bind = op.get_bind()
    rule_status_enum.create(bind, checkfirst=True)

    op.add_column("rules", sa.Column("status", rule_status_enum, nullable=False, server_default="active"))
    op.add_column("rules", sa.Column("effective_from", sa.DateTime(), nullable=True))
    op.add_column("rules", sa.Column("approved_by", sa.Integer(), nullable=True))
    op.add_column("rules", sa.Column("approved_at", sa.DateTime(), nullable=True))
    op.create_foreign_key("fk_rules_approved_by_user", "rules", "user", ["approved_by"], ["id"])

    op.add_column("rules_history", sa.Column("status", rule_status_enum, nullable=False, server_default="active"))
    op.add_column("rules_history", sa.Column("effective_from", sa.DateTime(), nullable=True))
    op.add_column("rules_history", sa.Column("approved_by", sa.Integer(), nullable=True))
    op.add_column("rules_history", sa.Column("approved_at", sa.DateTime(), nullable=True))
    op.alter_column("rules_history", "status", server_default=None)


def downgrade() -> None:
    op.drop_column("rules_history", "approved_at")
    op.drop_column("rules_history", "approved_by")
    op.drop_column("rules_history", "effective_from")
    op.drop_column("rules_history", "status")

    op.drop_constraint("fk_rules_approved_by_user", "rules", type_="foreignkey")
    op.drop_column("rules", "approved_at")
    op.drop_column("rules", "approved_by")
    op.drop_column("rules", "effective_from")
    op.drop_column("rules", "status")

    bind = op.get_bind()
    rule_status_enum.drop(bind, checkfirst=True)
