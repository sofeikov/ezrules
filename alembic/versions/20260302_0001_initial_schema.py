"""Initial schema baseline.

Revision ID: 20260302_0001
Revises:
Create Date: 2026-03-02 09:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260302_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "role",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=True),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("permissions", sa.UnicodeText(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "user",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("username", sa.String(length=255), nullable=True),
        sa.Column("password", sa.String(length=511), nullable=False),
        sa.Column("last_login_at", sa.DateTime(), nullable=True),
        sa.Column("current_login_at", sa.DateTime(), nullable=True),
        sa.Column("last_login_ip", sa.String(length=100), nullable=True),
        sa.Column("current_login_ip", sa.String(length=100), nullable=True),
        sa.Column("login_count", sa.Integer(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=True),
        sa.Column("fs_uniquifier", sa.String(length=64), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
        sa.UniqueConstraint("fs_uniquifier"),
        sa.UniqueConstraint("username"),
    )
    op.create_table(
        "organisation",
        sa.Column("o_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("o_id"),
        sa.UniqueConstraint("name"),
        sa.UniqueConstraint("o_id"),
    )
    op.create_table(
        "actions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("resource_type", sa.String(length=50), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "event_labels",
        sa.Column("el_id", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("el_id"),
        sa.UniqueConstraint("el_id"),
        sa.UniqueConstraint("label"),
    )
    op.create_table(
        "roles_users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("role_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["role_id"], ["role.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "role_actions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("role_id", sa.Integer(), nullable=False),
        sa.Column("action_id", sa.Integer(), nullable=False),
        sa.Column("resource_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["action_id"], ["actions.id"]),
        sa.ForeignKeyConstraint(["role_id"], ["role.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "rule_engine_config",
        sa.Column("re_id", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("o_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["o_id"], ["organisation.o_id"]),
        sa.PrimaryKeyConstraint("re_id"),
        sa.UniqueConstraint("re_id"),
    )
    op.create_table(
        "rules",
        sa.Column("r_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("rid", sa.String(), nullable=False),
        sa.Column("logic", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("o_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["o_id"], ["organisation.o_id"]),
        sa.PrimaryKeyConstraint("r_id"),
        sa.UniqueConstraint("r_id"),
    )
    op.create_table(
        "allowed_outcomes",
        sa.Column("ao_id", sa.Integer(), nullable=False),
        sa.Column("outcome_name", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("o_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["o_id"], ["organisation.o_id"]),
        sa.PrimaryKeyConstraint("ao_id"),
        sa.UniqueConstraint("ao_id"),
    )
    op.create_table(
        "user_lists",
        sa.Column("ul_id", sa.Integer(), nullable=False),
        sa.Column("list_name", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("o_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["o_id"], ["organisation.o_id"]),
        sa.PrimaryKeyConstraint("ul_id"),
        sa.UniqueConstraint("ul_id"),
    )
    op.create_table(
        "field_type_config",
        sa.Column("field_name", sa.String(), nullable=False),
        sa.Column("configured_type", sa.String(), nullable=False),
        sa.Column("datetime_format", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("o_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["o_id"], ["organisation.o_id"]),
        sa.PrimaryKeyConstraint("field_name", "o_id"),
    )
    op.create_table(
        "field_observation",
        sa.Column("field_name", sa.String(), nullable=False),
        sa.Column("observed_json_type", sa.String(), nullable=False),
        sa.Column("last_seen", sa.DateTime(), nullable=True),
        sa.Column("occurrence_count", sa.Integer(), nullable=False),
        sa.Column("o_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["o_id"], ["organisation.o_id"]),
        sa.PrimaryKeyConstraint("field_name", "observed_json_type", "o_id"),
    )
    op.create_table(
        "testing_record_log",
        sa.Column("tl_id", sa.Integer(), nullable=False),
        sa.Column("event", sa.JSON(), nullable=False),
        sa.Column("event_timestamp", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("o_id", sa.Integer(), nullable=False),
        sa.Column("el_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["el_id"], ["event_labels.el_id"]),
        sa.ForeignKeyConstraint(["o_id"], ["organisation.o_id"]),
        sa.PrimaryKeyConstraint("tl_id"),
        sa.UniqueConstraint("tl_id"),
    )
    op.create_table(
        "user_session",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("refresh_token", sa.String(length=2048), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("refresh_token"),
    )
    op.create_table(
        "api_keys",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("gid", sa.String(length=36), nullable=False),
        sa.Column("key_hash", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("o_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["o_id"], ["organisation.o_id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "user_list_entries",
        sa.Column("ule_id", sa.Integer(), nullable=False),
        sa.Column("entry_value", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("ul_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["ul_id"], ["user_lists.ul_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("ule_id"),
        sa.UniqueConstraint("ule_id"),
    )
    op.create_table(
        "rule_backtesting_results",
        sa.Column("bt_id", sa.Integer(), nullable=False),
        sa.Column("r_id", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.String(), nullable=False),
        sa.Column("stored_logic", sa.String(), nullable=True),
        sa.Column("proposed_logic", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["r_id"], ["rules.r_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("bt_id"),
        sa.UniqueConstraint("bt_id"),
    )
    op.create_table(
        "testing_results_log",
        sa.Column("tr_id", sa.Integer(), nullable=False),
        sa.Column("tl_id", sa.Integer(), nullable=False),
        sa.Column("rule_result", sa.String(), nullable=False),
        sa.Column("r_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["r_id"], ["rules.r_id"]),
        sa.ForeignKeyConstraint(["tl_id"], ["testing_record_log.tl_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("tr_id"),
        sa.UniqueConstraint("tr_id"),
    )
    op.create_table(
        "shadow_results_log",
        sa.Column("sr_id", sa.Integer(), nullable=False),
        sa.Column("tl_id", sa.Integer(), nullable=False),
        sa.Column("r_id", sa.Integer(), nullable=False),
        sa.Column("rule_result", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["r_id"], ["rules.r_id"]),
        sa.ForeignKeyConstraint(["tl_id"], ["testing_record_log.tl_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("sr_id"),
        sa.UniqueConstraint("sr_id"),
    )
    op.create_table(
        "rules_history",
        sa.Column("r_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("rid", sa.String(), nullable=False),
        sa.Column("logic", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("o_id", sa.Integer(), nullable=False),
        sa.Column("changed", sa.DateTime(), nullable=True),
        sa.Column("changed_by", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("r_id", "version"),
    )
    op.create_table(
        "rule_engine_config_history",
        sa.Column("re_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("o_id", sa.Integer(), nullable=False),
        sa.Column("changed", sa.DateTime(), nullable=True),
        sa.Column("changed_by", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("re_id", "version"),
    )
    op.create_table(
        "user_list_history",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("ul_id", sa.Integer(), nullable=False),
        sa.Column("list_name", sa.String(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("details", sa.String(), nullable=True),
        sa.Column("o_id", sa.Integer(), nullable=False),
        sa.Column("changed", sa.DateTime(), nullable=True),
        sa.Column("changed_by", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "outcome_history",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("ao_id", sa.Integer(), nullable=False),
        sa.Column("outcome_name", sa.String(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("o_id", sa.Integer(), nullable=False),
        sa.Column("changed", sa.DateTime(), nullable=True),
        sa.Column("changed_by", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "label_history",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("el_id", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("changed", sa.DateTime(), nullable=True),
        sa.Column("changed_by", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "user_account_history",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("user_email", sa.String(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("details", sa.String(), nullable=True),
        sa.Column("changed", sa.DateTime(), nullable=True),
        sa.Column("changed_by", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "role_permission_history",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("role_id", sa.Integer(), nullable=False),
        sa.Column("role_name", sa.String(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("details", sa.String(), nullable=True),
        sa.Column("changed", sa.DateTime(), nullable=True),
        sa.Column("changed_by", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "field_type_history",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("field_name", sa.String(), nullable=False),
        sa.Column("configured_type", sa.String(), nullable=False),
        sa.Column("datetime_format", sa.String(), nullable=True),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("details", sa.String(), nullable=True),
        sa.Column("o_id", sa.Integer(), nullable=False),
        sa.Column("changed", sa.DateTime(), nullable=True),
        sa.Column("changed_by", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "api_key_history",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("api_key_gid", sa.String(length=36), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("o_id", sa.Integer(), nullable=False),
        sa.Column("changed", sa.DateTime(), nullable=True),
        sa.Column("changed_by", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_session_user_id", "user_session", ["user_id"], unique=False)
    op.create_index("ix_api_keys_gid", "api_keys", ["gid"], unique=True)
    op.create_index("ix_api_key_history_api_key_gid", "api_key_history", ["api_key_gid"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_api_key_history_api_key_gid", table_name="api_key_history")
    op.drop_index("ix_api_keys_gid", table_name="api_keys")
    op.drop_index("ix_user_session_user_id", table_name="user_session")
    op.drop_table("api_key_history")
    op.drop_table("field_type_history")
    op.drop_table("role_permission_history")
    op.drop_table("user_account_history")
    op.drop_table("label_history")
    op.drop_table("outcome_history")
    op.drop_table("user_list_history")
    op.drop_table("rule_engine_config_history")
    op.drop_table("rules_history")
    op.drop_table("shadow_results_log")
    op.drop_table("testing_results_log")
    op.drop_table("rule_backtesting_results")
    op.drop_table("user_list_entries")
    op.drop_table("api_keys")
    op.drop_table("user_session")
    op.drop_table("testing_record_log")
    op.drop_table("field_observation")
    op.drop_table("field_type_config")
    op.drop_table("user_lists")
    op.drop_table("allowed_outcomes")
    op.drop_table("rules")
    op.drop_table("rule_engine_config")
    op.drop_table("role_actions")
    op.drop_table("roles_users")
    op.drop_table("event_labels")
    op.drop_table("actions")
    op.drop_table("organisation")
    op.drop_table("user")
    op.drop_table("role")
