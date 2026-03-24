"""Add reporting and admin indexes for audit, rollout, and history queries.

Revision ID: 20260324_0018
Revises: 20260324_0017
Create Date: 2026-03-24 14:05:00.000000
"""

from __future__ import annotations

from alembic import op


# revision identifiers, used by Alembic.
revision = "20260324_0018"
down_revision = "20260324_0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_roles_users_role_id_user_id", "roles_users", ["role_id", "user_id"], unique=False)
    op.create_index("ix_rule_backtesting_results_task_id", "rule_backtesting_results", ["task_id"], unique=False)
    op.create_index(
        "ix_rule_backtesting_results_r_id_created_at",
        "rule_backtesting_results",
        ["r_id", "created_at"],
        unique=False,
    )

    op.drop_index("ix_rule_quality_reports_lookup", table_name="rule_quality_reports")
    op.create_index(
        "ix_rule_quality_reports_cache_lookup",
        "rule_quality_reports",
        ["o_id", "min_support", "lookback_days", "pair_set_hash", "status", "created_at"],
        unique=False,
    )

    op.drop_index("ix_rule_deployment_results_log_o_id", table_name="rule_deployment_results_log")
    op.drop_index("ix_rule_deployment_results_log_mode", table_name="rule_deployment_results_log")
    op.create_index(
        "ix_rule_deployment_results_log_o_id_mode_dr_id",
        "rule_deployment_results_log",
        ["o_id", "mode", "dr_id"],
        unique=False,
    )
    op.create_index(
        "ix_rule_deployment_results_log_o_id_r_id",
        "rule_deployment_results_log",
        ["o_id", "r_id"],
        unique=False,
    )

    op.create_index("ix_rules_history_o_id_changed", "rules_history", ["o_id", "changed"], unique=False)
    op.create_index(
        "ix_rule_engine_config_history_o_id_changed",
        "rule_engine_config_history",
        ["o_id", "changed"],
        unique=False,
    )
    op.create_index(
        "ix_user_list_history_o_id_ul_id_changed", "user_list_history", ["o_id", "ul_id", "changed"], unique=False
    )
    op.create_index("ix_outcome_history_o_id_changed", "outcome_history", ["o_id", "changed"], unique=False)

    op.drop_index("ix_label_history_o_id", table_name="label_history")
    op.create_index("ix_label_history_o_id_changed", "label_history", ["o_id", "changed"], unique=False)

    op.drop_index("ix_user_account_history_o_id", table_name="user_account_history")
    op.create_index(
        "ix_user_account_history_o_id_user_id_changed",
        "user_account_history",
        ["o_id", "user_id", "changed"],
        unique=False,
    )

    op.drop_index("ix_role_permission_history_o_id", table_name="role_permission_history")
    op.create_index(
        "ix_role_permission_history_o_id_role_id_changed",
        "role_permission_history",
        ["o_id", "role_id", "changed"],
        unique=False,
    )

    op.create_index(
        "ix_field_type_history_o_id_field_name_changed",
        "field_type_history",
        ["o_id", "field_name", "changed"],
        unique=False,
    )
    op.create_index("ix_api_key_history_o_id_changed", "api_key_history", ["o_id", "changed"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_api_key_history_o_id_changed", table_name="api_key_history")
    op.drop_index("ix_field_type_history_o_id_field_name_changed", table_name="field_type_history")

    op.drop_index("ix_role_permission_history_o_id_role_id_changed", table_name="role_permission_history")
    op.create_index("ix_role_permission_history_o_id", "role_permission_history", ["o_id"], unique=False)

    op.drop_index("ix_user_account_history_o_id_user_id_changed", table_name="user_account_history")
    op.create_index("ix_user_account_history_o_id", "user_account_history", ["o_id"], unique=False)

    op.drop_index("ix_label_history_o_id_changed", table_name="label_history")
    op.create_index("ix_label_history_o_id", "label_history", ["o_id"], unique=False)

    op.drop_index("ix_outcome_history_o_id_changed", table_name="outcome_history")
    op.drop_index("ix_user_list_history_o_id_ul_id_changed", table_name="user_list_history")
    op.drop_index("ix_rule_engine_config_history_o_id_changed", table_name="rule_engine_config_history")
    op.drop_index("ix_rules_history_o_id_changed", table_name="rules_history")

    op.drop_index("ix_rule_deployment_results_log_o_id_r_id", table_name="rule_deployment_results_log")
    op.drop_index("ix_rule_deployment_results_log_o_id_mode_dr_id", table_name="rule_deployment_results_log")
    op.create_index("ix_rule_deployment_results_log_mode", "rule_deployment_results_log", ["mode"], unique=False)
    op.create_index("ix_rule_deployment_results_log_o_id", "rule_deployment_results_log", ["o_id"], unique=False)

    op.drop_index("ix_rule_quality_reports_cache_lookup", table_name="rule_quality_reports")
    op.create_index(
        "ix_rule_quality_reports_lookup",
        "rule_quality_reports",
        ["o_id", "min_support", "lookback_days", "created_at"],
        unique=False,
    )

    op.drop_index("ix_rule_backtesting_results_r_id_created_at", table_name="rule_backtesting_results")
    op.drop_index("ix_rule_backtesting_results_task_id", table_name="rule_backtesting_results")
    op.drop_index("ix_roles_users_role_id_user_id", table_name="roles_users")
