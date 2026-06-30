"""Snapshot evaluation rule metadata.

Revision ID: 20260625_0032
Revises: 20260604_0031
Create Date: 2026-06-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260625_0032"
down_revision: str | None = "20260604_0031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("evaluation_rule_results", sa.Column("rule_rid", sa.String(), nullable=True))
    op.add_column("evaluation_rule_results", sa.Column("rule_description", sa.String(), nullable=True))
    op.add_column("evaluation_rule_results", sa.Column("rule_logic", sa.Text(), nullable=True))
    op.add_column("evaluation_rule_results", sa.Column("referenced_fields", postgresql.JSONB(), nullable=True))
    op.add_column(
        "evaluation_rule_results",
        sa.Column("metadata_source", sa.String(length=32), nullable=False, server_default="evaluation_snapshot"),
    )
    op.alter_column("evaluation_rule_results", "metadata_source", server_default=None)


def downgrade() -> None:
    op.drop_column("evaluation_rule_results", "metadata_source")
    op.drop_column("evaluation_rule_results", "referenced_fields")
    op.drop_column("evaluation_rule_results", "rule_logic")
    op.drop_column("evaluation_rule_results", "rule_description")
    op.drop_column("evaluation_rule_results", "rule_rid")
