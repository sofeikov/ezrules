"""add rule history action metadata

Revision ID: 20260303_0003
Revises: 20260303_0002
Create Date: 2026-03-03 18:10:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "20260303_0003"
down_revision = "20260303_0002"
branch_labels = None
depends_on = None


rule_status_enum = postgresql.ENUM("draft", "active", "archived", name="rule_status_enum", create_type=False)


def upgrade() -> None:
    op.add_column("rules_history", sa.Column("action", sa.String(), nullable=False, server_default="updated"))
    op.add_column("rules_history", sa.Column("to_status", rule_status_enum, nullable=True))
    op.alter_column("rules_history", "action", server_default=None)


def downgrade() -> None:
    op.drop_column("rules_history", "to_status")
    op.drop_column("rules_history", "action")
