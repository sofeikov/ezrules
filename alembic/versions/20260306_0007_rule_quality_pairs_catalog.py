"""Add curated rule-quality pairs and pair-set cache key fields.

Revision ID: 20260306_0007
Revises: 20260306_0006
Create Date: 2026-03-06 19:45:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260306_0007"
down_revision = "20260306_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "rule_quality_pairs",
        sa.Column("rqp_id", sa.Integer(), nullable=False),
        sa.Column("outcome", sa.String(length=255), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column("o_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["o_id"], ["organisation.o_id"]),
        sa.PrimaryKeyConstraint("rqp_id"),
        sa.UniqueConstraint("o_id", "outcome", "label", name="uq_rule_quality_pairs_org_outcome_label"),
    )
    op.create_index("ix_rule_quality_pairs_o_id_active", "rule_quality_pairs", ["o_id", "active"], unique=False)

    op.add_column(
        "rule_quality_reports",
        sa.Column(
            "pair_set_hash",
            sa.String(length=64),
            nullable=False,
            server_default=sa.text("'legacy'"),
        ),
    )
    op.add_column(
        "rule_quality_reports",
        sa.Column(
            "pair_set",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'::json"),
        ),
    )
    op.create_index("ix_rule_quality_reports_pair_set_hash", "rule_quality_reports", ["pair_set_hash"], unique=False)

    with op.batch_alter_table("rule_quality_pairs") as batch_op:
        batch_op.alter_column("active", server_default=None)
    with op.batch_alter_table("rule_quality_reports") as batch_op:
        batch_op.alter_column("pair_set_hash", server_default=None)
        batch_op.alter_column("pair_set", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_rule_quality_reports_pair_set_hash", table_name="rule_quality_reports")
    with op.batch_alter_table("rule_quality_reports") as batch_op:
        batch_op.drop_column("pair_set")
        batch_op.drop_column("pair_set_hash")

    op.drop_index("ix_rule_quality_pairs_o_id_active", table_name="rule_quality_pairs")
    op.drop_table("rule_quality_pairs")
