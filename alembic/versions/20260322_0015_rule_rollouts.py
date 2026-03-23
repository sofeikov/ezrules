"""Add rollout comparison logging table.

Revision ID: 20260322_0015
Revises: 20260318_0014
Create Date: 2026-03-22 10:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260322_0015"
down_revision = "20260318_0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "rule_deployment_results_log",
        sa.Column("dr_id", sa.Integer(), nullable=False),
        sa.Column("tl_id", sa.Integer(), nullable=False),
        sa.Column("r_id", sa.Integer(), nullable=False),
        sa.Column("o_id", sa.Integer(), nullable=False),
        sa.Column("mode", sa.String(length=20), nullable=False),
        sa.Column("selected_variant", sa.String(length=20), nullable=False),
        sa.Column("traffic_percent", sa.Integer(), nullable=True),
        sa.Column("bucket", sa.Integer(), nullable=True),
        sa.Column("control_result", sa.String(), nullable=True),
        sa.Column("candidate_result", sa.String(), nullable=True),
        sa.Column("returned_result", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["o_id"], ["organisation.o_id"]),
        sa.ForeignKeyConstraint(["r_id"], ["rules.r_id"]),
        sa.ForeignKeyConstraint(["tl_id"], ["testing_record_log.tl_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("dr_id"),
        sa.UniqueConstraint("dr_id"),
    )
    op.create_index(
        "ix_rule_deployment_results_log_mode",
        "rule_deployment_results_log",
        ["mode"],
        unique=False,
    )
    op.create_index(
        "ix_rule_deployment_results_log_o_id",
        "rule_deployment_results_log",
        ["o_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_rule_deployment_results_log_o_id", table_name="rule_deployment_results_log")
    op.drop_index("ix_rule_deployment_results_log_mode", table_name="rule_deployment_results_log")
    op.drop_table("rule_deployment_results_log")
