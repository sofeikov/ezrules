"""Add dedicated rule-quality report generation permission.

Revision ID: 20260707_0037
Revises: 20260707_0036
Create Date: 2026-07-07 12:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260707_0037"
down_revision = "20260707_0036"
branch_labels = None
depends_on = None


ACTION_NAME = "generate_rule_quality_reports"
ACTION_DESCRIPTION = "Generate rule-quality report snapshots"
RESOURCE_TYPE = "rule"
DEFAULT_ROLE_NAMES = ("admin", "rule_editor")


def upgrade() -> None:
    conn = op.get_bind()

    conn.execute(
        sa.text(
            """
            INSERT INTO actions (name, description, resource_type, created_at)
            SELECT :name, :description, :resource_type, NOW()
            WHERE EXISTS (
                SELECT 1
                FROM actions
            )
              AND NOT EXISTS (
                SELECT 1
                FROM actions
                WHERE name = :name
            )
            """
        ),
        {
            "name": ACTION_NAME,
            "description": ACTION_DESCRIPTION,
            "resource_type": RESOURCE_TYPE,
        },
    )

    action_id = conn.execute(
        sa.text(
            """
            SELECT id
            FROM actions
            WHERE name = :name
            """
        ),
        {"name": ACTION_NAME},
    ).scalar_one_or_none()

    if action_id is None:
        return

    role_ids = conn.execute(
        sa.text(
            """
            SELECT id
            FROM "role"
            WHERE name IN :role_names
            """
        ).bindparams(sa.bindparam("role_names", expanding=True)),
        {"role_names": DEFAULT_ROLE_NAMES},
    ).scalars()

    for role_id in role_ids:
        conn.execute(
            sa.text(
                """
                INSERT INTO role_actions (role_id, action_id, resource_id, created_at)
                SELECT :role_id, :action_id, NULL, NOW()
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM role_actions
                    WHERE role_id = :role_id
                      AND action_id = :action_id
                      AND resource_id IS NULL
                )
                """
            ),
            {
                "role_id": int(role_id),
                "action_id": int(action_id),
            },
        )


def downgrade() -> None:
    conn = op.get_bind()

    action_id = conn.execute(
        sa.text(
            """
            SELECT id
            FROM actions
            WHERE name = :name
            """
        ),
        {"name": ACTION_NAME},
    ).scalar_one_or_none()

    if action_id is None:
        return

    conn.execute(
        sa.text(
            """
            DELETE FROM role_actions
            WHERE action_id = :action_id
            """
        ),
        {"action_id": int(action_id)},
    )
    conn.execute(
        sa.text(
            """
            DELETE FROM actions
            WHERE id = :action_id
            """
        ),
        {"action_id": int(action_id)},
    )
