"""add canonical evaluation ledgers

Revision ID: 20260428_0025
Revises: 20260421_0024
Create Date: 2026-04-28 12:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260428_0025"
down_revision = "20260421_0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "event_versions",
        sa.Column("ev_id", sa.Integer(), nullable=False),
        sa.Column("o_id", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.String(), nullable=False),
        sa.Column("event_version", sa.Integer(), nullable=False),
        sa.Column("event_timestamp", sa.Integer(), nullable=False),
        sa.Column("event_data", sa.JSON(), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("supersedes_ev_id", sa.Integer(), nullable=True),
        sa.Column("ingested_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["o_id"], ["organisation.o_id"]),
        sa.ForeignKeyConstraint(["supersedes_ev_id"], ["event_versions.ev_id"]),
        sa.PrimaryKeyConstraint("ev_id"),
        sa.UniqueConstraint("ev_id"),
        sa.UniqueConstraint("o_id", "event_id", "event_version", name="uq_event_versions_org_event_version"),
    )
    op.create_index(
        "ix_event_versions_o_id_event_id_version",
        "event_versions",
        ["o_id", "event_id", "event_version"],
        unique=False,
    )
    op.create_index("ix_event_versions_o_id_event_timestamp", "event_versions", ["o_id", "event_timestamp"])
    op.create_index("ix_event_versions_o_id_ingested_at", "event_versions", ["o_id", "ingested_at"])

    op.create_table(
        "evaluation_decisions",
        sa.Column("ed_id", sa.Integer(), nullable=False),
        sa.Column("ev_id", sa.Integer(), nullable=False),
        sa.Column("tl_id", sa.Integer(), nullable=True),
        sa.Column("o_id", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.String(), nullable=False),
        sa.Column("event_version", sa.Integer(), nullable=False),
        sa.Column("event_timestamp", sa.Integer(), nullable=False),
        sa.Column("decision_type", sa.String(length=32), nullable=False),
        sa.Column("served", sa.Boolean(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("rule_config_label", sa.String(length=64), nullable=False),
        sa.Column("rule_config_version", sa.Integer(), nullable=True),
        sa.Column("runtime_config", sa.JSON(), nullable=True),
        sa.Column("outcome_counters", sa.JSON(), nullable=True),
        sa.Column("resolved_outcome", sa.String(), nullable=True),
        sa.Column("all_rule_results", sa.JSON(), nullable=True),
        sa.Column("evaluated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["ev_id"], ["event_versions.ev_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["o_id"], ["organisation.o_id"]),
        sa.ForeignKeyConstraint(["tl_id"], ["testing_record_log.tl_id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("ed_id"),
        sa.UniqueConstraint("ed_id"),
        sa.UniqueConstraint("o_id", "idempotency_key", name="uq_evaluation_decisions_org_idempotency_key"),
    )
    op.create_index(
        "ix_evaluation_decisions_o_id_evaluated_at",
        "evaluation_decisions",
        ["o_id", "evaluated_at"],
        unique=False,
    )
    op.create_index(
        "ix_evaluation_decisions_o_id_event_id_version",
        "evaluation_decisions",
        ["o_id", "event_id", "event_version"],
        unique=False,
    )
    op.create_index("ix_evaluation_decisions_o_id_served", "evaluation_decisions", ["o_id", "served"])

    op.create_table(
        "evaluation_rule_results",
        sa.Column("err_id", sa.Integer(), nullable=False),
        sa.Column("ed_id", sa.Integer(), nullable=False),
        sa.Column("r_id", sa.Integer(), nullable=False),
        sa.Column("rule_result", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["ed_id"], ["evaluation_decisions.ed_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["r_id"], ["rules.r_id"]),
        sa.PrimaryKeyConstraint("err_id"),
        sa.UniqueConstraint("err_id"),
    )
    op.create_index(
        "ix_evaluation_rule_results_ed_id_r_id",
        "evaluation_rule_results",
        ["ed_id", "r_id"],
        unique=False,
    )
    op.create_index("ix_evaluation_rule_results_r_id", "evaluation_rule_results", ["r_id"], unique=False)

    op.add_column("shadow_results_log", sa.Column("ed_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_shadow_results_log_ed_id_evaluation_decisions",
        "shadow_results_log",
        "evaluation_decisions",
        ["ed_id"],
        ["ed_id"],
        ondelete="SET NULL",
    )
    op.add_column("rule_deployment_results_log", sa.Column("ed_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_rule_deployment_results_log_ed_id_evaluation_decisions",
        "rule_deployment_results_log",
        "evaluation_decisions",
        ["ed_id"],
        ["ed_id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_rule_deployment_results_log_ed_id",
        "rule_deployment_results_log",
        ["ed_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_rule_deployment_results_log_ed_id", table_name="rule_deployment_results_log")
    op.drop_constraint(
        "fk_rule_deployment_results_log_ed_id_evaluation_decisions",
        "rule_deployment_results_log",
        type_="foreignkey",
    )
    op.drop_column("rule_deployment_results_log", "ed_id")
    op.drop_constraint("fk_shadow_results_log_ed_id_evaluation_decisions", "shadow_results_log", type_="foreignkey")
    op.drop_column("shadow_results_log", "ed_id")

    op.drop_index("ix_evaluation_rule_results_r_id", table_name="evaluation_rule_results")
    op.drop_index("ix_evaluation_rule_results_ed_id_r_id", table_name="evaluation_rule_results")
    op.drop_table("evaluation_rule_results")

    op.drop_index("ix_evaluation_decisions_o_id_served", table_name="evaluation_decisions")
    op.drop_index("ix_evaluation_decisions_o_id_event_id_version", table_name="evaluation_decisions")
    op.drop_index("ix_evaluation_decisions_o_id_evaluated_at", table_name="evaluation_decisions")
    op.drop_table("evaluation_decisions")

    op.drop_index("ix_event_versions_o_id_ingested_at", table_name="event_versions")
    op.drop_index("ix_event_versions_o_id_event_timestamp", table_name="event_versions")
    op.drop_index("ix_event_versions_o_id_event_id_version", table_name="event_versions")
    op.drop_table("event_versions")
