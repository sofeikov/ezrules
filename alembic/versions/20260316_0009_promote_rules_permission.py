"""Add dedicated promote-rules permission.

Revision ID: 20260316_0009
Revises: 20260311_0008
Create Date: 2026-03-16 10:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260316_0009"
down_revision = "20260311_0008"
branch_labels = None
depends_on = None


ACTION_NAME = "promote_rules"
ACTION_DESCRIPTION = "Promote draft or shadow rules to production"
RESOURCE_TYPE = "rule"


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

    admin_role_ids = conn.execute(
        sa.text(
            """
            SELECT id
            FROM "role"
            WHERE name = :role_name
            """
        ),
        {"role_name": "admin"},
    ).scalars()

    for role_id in admin_role_ids:
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
