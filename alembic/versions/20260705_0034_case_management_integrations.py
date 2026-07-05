"""Add case management and integration event outbox.

Revision ID: 20260705_0034
Revises: 20260630_0033
Create Date: 2026-07-05
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260705_0034"
down_revision: str | None = "20260630_0033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "cases",
        sa.Column("case_id", sa.Integer(), nullable=False),
        sa.Column("o_id", sa.Integer(), nullable=False),
        sa.Column("transaction_id", sa.String(), nullable=False),
        sa.Column("current_ev_id", sa.Integer(), nullable=False),
        sa.Column("current_ed_id", sa.Integer(), nullable=False),
        sa.Column("opened_by_ed_id", sa.Integer(), nullable=False),
        sa.Column("previous_ed_id", sa.Integer(), nullable=True),
        sa.Column("resolved_outcome", sa.String(length=255), nullable=True),
        sa.Column("previous_resolved_outcome", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("decision_state", sa.String(length=32), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("assigned_to_user_id", sa.Integer(), nullable=True),
        sa.Column("resolved_by_user_id", sa.Integer(), nullable=True),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.Column("resolution_label_id", sa.Integer(), nullable=True),
        sa.Column("reopened_from_case_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["assigned_to_user_id"], ["user.id"]),
        sa.ForeignKeyConstraint(["current_ed_id"], ["evaluation_decisions.ed_id"]),
        sa.ForeignKeyConstraint(["current_ev_id"], ["event_versions.ev_id"]),
        sa.ForeignKeyConstraint(["o_id"], ["organisation.o_id"]),
        sa.ForeignKeyConstraint(["opened_by_ed_id"], ["evaluation_decisions.ed_id"]),
        sa.ForeignKeyConstraint(["previous_ed_id"], ["evaluation_decisions.ed_id"]),
        sa.ForeignKeyConstraint(["reopened_from_case_id"], ["cases.case_id"]),
        sa.ForeignKeyConstraint(["resolution_label_id"], ["event_labels.el_id"]),
        sa.ForeignKeyConstraint(["resolved_by_user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("case_id"),
        sa.UniqueConstraint("case_id"),
    )
    op.create_index("ix_cases_o_id_current_ed", "cases", ["o_id", "current_ed_id"])
    op.create_index("ix_cases_o_id_status_updated", "cases", ["o_id", "status", "updated_at"])
    op.create_index("ix_cases_o_id_transaction", "cases", ["o_id", "transaction_id"])
    op.create_index(
        "uq_cases_active_org_transaction",
        "cases",
        ["o_id", "transaction_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('open', 'in_review', 'reopened')"),
    )

    op.create_table(
        "case_events",
        sa.Column("case_event_id", sa.Integer(), nullable=False),
        sa.Column("case_id", sa.Integer(), nullable=False),
        sa.Column("o_id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("source_ed_id", sa.Integer(), nullable=True),
        sa.Column("external_event_id", sa.String(length=64), nullable=False),
        sa.Column("occurred_at", sa.DateTime(), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["user.id"]),
        sa.ForeignKeyConstraint(["case_id"], ["cases.case_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["o_id"], ["organisation.o_id"]),
        sa.ForeignKeyConstraint(["source_ed_id"], ["evaluation_decisions.ed_id"]),
        sa.PrimaryKeyConstraint("case_event_id"),
        sa.UniqueConstraint("case_event_id"),
        sa.UniqueConstraint("external_event_id", name="uq_case_events_external_event_id"),
    )
    op.create_index("ix_case_events_case_id_created", "case_events", ["case_id", "created_at"])
    op.create_index("ix_case_events_o_id_created", "case_events", ["o_id", "created_at"])

    op.create_table(
        "integration_events",
        sa.Column("integration_event_id", sa.Integer(), nullable=False),
        sa.Column("external_event_id", sa.String(length=64), nullable=False),
        sa.Column("o_id", sa.Integer(), nullable=False),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("event_version", sa.Integer(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["o_id"], ["organisation.o_id"]),
        sa.PrimaryKeyConstraint("integration_event_id"),
        sa.UniqueConstraint("external_event_id", name="uq_integration_events_external_event_id"),
        sa.UniqueConstraint("integration_event_id"),
    )
    op.create_index("ix_integration_events_o_id_created", "integration_events", ["o_id", "created_at"])
    op.create_index("ix_integration_events_o_id_source", "integration_events", ["o_id", "source_type", "source_id"])
    op.create_index(
        "ix_integration_events_o_id_type_created",
        "integration_events",
        ["o_id", "event_type", "created_at"],
    )

    op.create_table(
        "integration_subscriptions",
        sa.Column("subscription_id", sa.Integer(), nullable=False),
        sa.Column("o_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("destination_type", sa.String(length=64), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("secret_ref", sa.String(length=255), nullable=True),
        sa.Column("event_types", sa.JSON(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["o_id"], ["organisation.o_id"]),
        sa.PrimaryKeyConstraint("subscription_id"),
        sa.UniqueConstraint("o_id", "name", name="uq_integration_subscriptions_org_name"),
        sa.UniqueConstraint("subscription_id"),
    )
    op.create_index(
        "ix_integration_subscriptions_o_id_enabled",
        "integration_subscriptions",
        ["o_id", "enabled"],
    )

    op.create_table(
        "integration_outbox",
        sa.Column("delivery_id", sa.Integer(), nullable=False),
        sa.Column("o_id", sa.Integer(), nullable=False),
        sa.Column("integration_event_id", sa.Integer(), nullable=False),
        sa.Column("subscription_id", sa.Integer(), nullable=False),
        sa.Column("destination_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(), nullable=False),
        sa.Column("last_attempted_at", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["integration_event_id"], ["integration_events.integration_event_id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["o_id"], ["organisation.o_id"]),
        sa.ForeignKeyConstraint(["subscription_id"], ["integration_subscriptions.subscription_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("delivery_id"),
        sa.UniqueConstraint("delivery_id"),
        sa.UniqueConstraint("integration_event_id", "subscription_id", name="uq_integration_outbox_event_subscription"),
    )
    op.create_index("ix_integration_outbox_o_id_created", "integration_outbox", ["o_id", "created_at"])
    op.create_index("ix_integration_outbox_status_next", "integration_outbox", ["status", "next_attempt_at"])


def downgrade() -> None:
    op.drop_index("ix_integration_outbox_status_next", table_name="integration_outbox")
    op.drop_index("ix_integration_outbox_o_id_created", table_name="integration_outbox")
    op.drop_table("integration_outbox")
    op.drop_index("ix_integration_subscriptions_o_id_enabled", table_name="integration_subscriptions")
    op.drop_table("integration_subscriptions")
    op.drop_index("ix_integration_events_o_id_type_created", table_name="integration_events")
    op.drop_index("ix_integration_events_o_id_source", table_name="integration_events")
    op.drop_index("ix_integration_events_o_id_created", table_name="integration_events")
    op.drop_table("integration_events")
    op.drop_index("ix_case_events_o_id_created", table_name="case_events")
    op.drop_index("ix_case_events_case_id_created", table_name="case_events")
    op.drop_table("case_events")
    op.drop_index("uq_cases_active_org_transaction", table_name="cases")
    op.drop_index("ix_cases_o_id_transaction", table_name="cases")
    op.drop_index("ix_cases_o_id_status_updated", table_name="cases")
    op.drop_index("ix_cases_o_id_current_ed", table_name="cases")
    op.drop_table("cases")
