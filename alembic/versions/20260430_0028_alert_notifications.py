"""add alert rules and notification inbox

Revision ID: 20260430_0028
Revises: 20260429_0028
Create Date: 2026-04-30 10:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260430_0028"
down_revision = "20260429_0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "alert_rules",
        sa.Column("ar_id", sa.Integer(), nullable=False),
        sa.Column("o_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("outcome", sa.String(length=255), nullable=False),
        sa.Column("threshold", sa.Integer(), nullable=False),
        sa.Column("window_seconds", sa.Integer(), nullable=False),
        sa.Column("cooldown_seconds", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["o_id"], ["organisation.o_id"]),
        sa.PrimaryKeyConstraint("ar_id"),
        sa.UniqueConstraint("ar_id"),
        sa.UniqueConstraint("o_id", "name", name="uq_alert_rules_org_name"),
    )
    op.create_index("ix_alert_rules_o_id_outcome_enabled", "alert_rules", ["o_id", "outcome", "enabled"])

    op.create_table(
        "alert_incidents",
        sa.Column("ai_id", sa.Integer(), nullable=False),
        sa.Column("o_id", sa.Integer(), nullable=False),
        sa.Column("alert_rule_id", sa.Integer(), nullable=False),
        sa.Column("outcome", sa.String(length=255), nullable=False),
        sa.Column("observed_count", sa.Integer(), nullable=False),
        sa.Column("threshold", sa.Integer(), nullable=False),
        sa.Column("window_start", sa.DateTime(), nullable=False),
        sa.Column("window_end", sa.DateTime(), nullable=False),
        sa.Column("dedupe_key", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("triggered_at", sa.DateTime(), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(), nullable=True),
        sa.Column("acknowledged_by", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(["alert_rule_id"], ["alert_rules.ar_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["o_id"], ["organisation.o_id"]),
        sa.PrimaryKeyConstraint("ai_id"),
        sa.UniqueConstraint("ai_id"),
        sa.UniqueConstraint("alert_rule_id", "dedupe_key", name="uq_alert_incidents_rule_dedupe"),
    )
    op.create_index("ix_alert_incidents_alert_rule_status", "alert_incidents", ["alert_rule_id", "status"])
    op.create_index("ix_alert_incidents_o_id_triggered_at", "alert_incidents", ["o_id", "triggered_at"])

    op.create_table(
        "notification_channels",
        sa.Column("nc_id", sa.Integer(), nullable=False),
        sa.Column("o_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("channel_type", sa.String(length=64), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["o_id"], ["organisation.o_id"]),
        sa.PrimaryKeyConstraint("nc_id"),
        sa.UniqueConstraint("nc_id"),
        sa.UniqueConstraint("o_id", "name", name="uq_notification_channels_org_name"),
    )
    op.create_index(
        "ix_notification_channels_o_id_type_enabled",
        "notification_channels",
        ["o_id", "channel_type", "enabled"],
    )

    op.create_table(
        "notification_policies",
        sa.Column("np_id", sa.Integer(), nullable=False),
        sa.Column("o_id", sa.Integer(), nullable=False),
        sa.Column("alert_rule_id", sa.Integer(), nullable=False),
        sa.Column("notification_channel_id", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["alert_rule_id"], ["alert_rules.ar_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["notification_channel_id"], ["notification_channels.nc_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["o_id"], ["organisation.o_id"]),
        sa.PrimaryKeyConstraint("np_id"),
        sa.UniqueConstraint("np_id"),
        sa.UniqueConstraint("alert_rule_id", "notification_channel_id", name="uq_notification_policies_rule_channel"),
    )
    op.create_index(
        "ix_notification_policies_alert_rule_enabled",
        "notification_policies",
        ["alert_rule_id", "enabled"],
    )

    op.create_table(
        "notification_attempts",
        sa.Column("na_id", sa.Integer(), nullable=False),
        sa.Column("o_id", sa.Integer(), nullable=False),
        sa.Column("alert_incident_id", sa.Integer(), nullable=False),
        sa.Column("notification_channel_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("error", sa.String(), nullable=True),
        sa.Column("attempted_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["alert_incident_id"], ["alert_incidents.ai_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["notification_channel_id"], ["notification_channels.nc_id"]),
        sa.ForeignKeyConstraint(["o_id"], ["organisation.o_id"]),
        sa.PrimaryKeyConstraint("na_id"),
        sa.UniqueConstraint("na_id"),
    )
    op.create_index(
        "ix_notification_attempts_incident_channel",
        "notification_attempts",
        ["alert_incident_id", "notification_channel_id"],
    )
    op.create_index("ix_notification_attempts_o_id_attempted_at", "notification_attempts", ["o_id", "attempted_at"])

    op.create_table(
        "in_app_notifications",
        sa.Column("ian_id", sa.Integer(), nullable=False),
        sa.Column("o_id", sa.Integer(), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("body", sa.String(), nullable=False),
        sa.Column("action_url", sa.String(length=512), nullable=True),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["o_id"], ["organisation.o_id"]),
        sa.PrimaryKeyConstraint("ian_id"),
        sa.UniqueConstraint("ian_id"),
    )
    op.create_index("ix_in_app_notifications_o_id_created_at", "in_app_notifications", ["o_id", "created_at"])
    op.create_index(
        "ix_in_app_notifications_o_id_source",
        "in_app_notifications",
        ["o_id", "source_type", "source_id"],
    )

    op.create_table(
        "in_app_notification_reads",
        sa.Column("ianr_id", sa.Integer(), nullable=False),
        sa.Column("notification_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("read_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["notification_id"], ["in_app_notifications.ian_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("ianr_id"),
        sa.UniqueConstraint("ianr_id"),
        sa.UniqueConstraint("notification_id", "user_id", name="uq_in_app_notification_reads_notification_user"),
    )
    op.create_index("ix_in_app_notification_reads_user_read_at", "in_app_notification_reads", ["user_id", "read_at"])

    op.create_index(
        "ix_evaluation_decisions_o_id_resolved_evaluated_at",
        "evaluation_decisions",
        ["o_id", "resolved_outcome", "evaluated_at"],
    )

    op.create_table(
        "alert_rule_history",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("alert_rule_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("details", sa.String(), nullable=True),
        sa.Column("o_id", sa.Integer(), nullable=False),
        sa.Column("changed", sa.DateTime(), nullable=True),
        sa.Column("changed_by", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["o_id"], ["organisation.o_id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_alert_rule_history_o_id_changed", "alert_rule_history", ["o_id", "changed"])


def downgrade() -> None:
    op.drop_index("ix_alert_rule_history_o_id_changed", table_name="alert_rule_history")
    op.drop_table("alert_rule_history")
    op.drop_index("ix_evaluation_decisions_o_id_resolved_evaluated_at", table_name="evaluation_decisions")
    op.drop_index("ix_in_app_notification_reads_user_read_at", table_name="in_app_notification_reads")
    op.drop_table("in_app_notification_reads")
    op.drop_index("ix_in_app_notifications_o_id_source", table_name="in_app_notifications")
    op.drop_index("ix_in_app_notifications_o_id_created_at", table_name="in_app_notifications")
    op.drop_table("in_app_notifications")
    op.drop_index("ix_notification_attempts_o_id_attempted_at", table_name="notification_attempts")
    op.drop_index("ix_notification_attempts_incident_channel", table_name="notification_attempts")
    op.drop_table("notification_attempts")
    op.drop_index("ix_notification_policies_alert_rule_enabled", table_name="notification_policies")
    op.drop_table("notification_policies")
    op.drop_index("ix_notification_channels_o_id_type_enabled", table_name="notification_channels")
    op.drop_table("notification_channels")
    op.drop_index("ix_alert_incidents_o_id_triggered_at", table_name="alert_incidents")
    op.drop_index("ix_alert_incidents_alert_rule_status", table_name="alert_incidents")
    op.drop_table("alert_incidents")
    op.drop_index("ix_alert_rules_o_id_outcome_enabled", table_name="alert_rules")
    op.drop_table("alert_rules")
