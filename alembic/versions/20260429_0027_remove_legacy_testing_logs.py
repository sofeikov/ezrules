"""remove legacy testing event logs

Revision ID: 20260429_0027
Revises: 20260428_0026
Create Date: 2026-04-29 09:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260429_0027"
down_revision = "20260428_0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint("uq_event_versions_org_ev_id", "event_versions", ["o_id", "ev_id"])
    op.create_foreign_key(
        "fk_event_version_labels_event_version_org",
        "event_version_labels",
        "event_versions",
        ["o_id", "ev_id"],
        ["o_id", "ev_id"],
        ondelete="CASCADE",
    )

    op.execute("ALTER TABLE evaluation_decisions DROP CONSTRAINT IF EXISTS evaluation_decisions_tl_id_fkey")
    op.execute("ALTER TABLE shadow_results_log DROP CONSTRAINT IF EXISTS shadow_results_log_tl_id_fkey")
    op.execute(
        "ALTER TABLE rule_deployment_results_log DROP CONSTRAINT IF EXISTS rule_deployment_results_log_tl_id_fkey"
    )

    op.drop_column("evaluation_decisions", "tl_id")
    op.drop_column("shadow_results_log", "tl_id")
    op.drop_column("rule_deployment_results_log", "tl_id")

    op.alter_column("shadow_results_log", "ed_id", existing_type=sa.Integer(), nullable=False)
    op.alter_column("rule_deployment_results_log", "ed_id", existing_type=sa.Integer(), nullable=False)
    op.drop_table("testing_results_log")
    op.drop_table("testing_record_log")


def downgrade() -> None:
    op.drop_constraint("fk_event_version_labels_event_version_org", "event_version_labels", type_="foreignkey")
    op.drop_constraint("uq_event_versions_org_ev_id", "event_versions", type_="unique")

    op.create_table(
        "testing_record_log",
        sa.Column("tl_id", sa.Integer(), nullable=False),
        sa.Column("event", sa.JSON(), nullable=False),
        sa.Column("event_timestamp", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.String(), nullable=False),
        sa.Column("outcome_counters", sa.JSON(), nullable=True),
        sa.Column("resolved_outcome", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("o_id", sa.Integer(), nullable=False),
        sa.Column("el_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["o_id"], ["organisation.o_id"]),
        sa.ForeignKeyConstraint(["el_id", "o_id"], ["event_labels.el_id", "event_labels.o_id"]),
        sa.PrimaryKeyConstraint("tl_id"),
        sa.UniqueConstraint("tl_id"),
    )
    op.create_table(
        "testing_results_log",
        sa.Column("tr_id", sa.Integer(), nullable=False),
        sa.Column("tl_id", sa.Integer(), nullable=False),
        sa.Column("rule_result", sa.String(), nullable=False),
        sa.Column("r_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["tl_id"], ["testing_record_log.tl_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["r_id"], ["rules.r_id"]),
        sa.PrimaryKeyConstraint("tr_id"),
        sa.UniqueConstraint("tr_id"),
    )
    op.add_column("rule_deployment_results_log", sa.Column("tl_id", sa.Integer(), nullable=True))
    op.add_column("shadow_results_log", sa.Column("tl_id", sa.Integer(), nullable=True))
    op.add_column("evaluation_decisions", sa.Column("tl_id", sa.Integer(), nullable=True))
