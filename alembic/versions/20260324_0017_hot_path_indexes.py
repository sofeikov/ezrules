"""Add hot-path indexes for auth and event log queries.

Revision ID: 20260324_0017
Revises: 20260324_0016
Create Date: 2026-03-24 14:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260324_0017"
down_revision = "20260324_0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_api_keys_active_key_hash",
        "api_keys",
        ["key_hash"],
        unique=False,
        postgresql_where=sa.text("revoked_at IS NULL"),
    )
    op.create_index(
        "ix_role_actions_role_id_action_id_resource_id",
        "role_actions",
        ["role_id", "action_id", "resource_id"],
        unique=False,
    )
    op.create_index(
        "ix_testing_record_log_o_id_event_id",
        "testing_record_log",
        ["o_id", "event_id"],
        unique=False,
    )
    op.create_index(
        "ix_testing_record_log_o_id_tl_id",
        "testing_record_log",
        ["o_id", "tl_id"],
        unique=False,
    )
    op.create_index(
        "ix_testing_record_log_o_id_created_at",
        "testing_record_log",
        ["o_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_testing_results_log_tl_id_r_id",
        "testing_results_log",
        ["tl_id", "r_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_testing_results_log_tl_id_r_id", table_name="testing_results_log")
    op.drop_index("ix_testing_record_log_o_id_created_at", table_name="testing_record_log")
    op.drop_index("ix_testing_record_log_o_id_tl_id", table_name="testing_record_log")
    op.drop_index("ix_testing_record_log_o_id_event_id", table_name="testing_record_log")
    op.drop_index("ix_role_actions_role_id_action_id_resource_id", table_name="role_actions")
    op.drop_index("ix_api_keys_active_key_hash", table_name="api_keys", postgresql_where=sa.text("revoked_at IS NULL"))
