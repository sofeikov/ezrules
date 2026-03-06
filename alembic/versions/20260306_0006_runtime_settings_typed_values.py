"""Migrate runtime settings to typed value storage.

Revision ID: 20260306_0006
Revises: 20260306_0005
Create Date: 2026-03-06 18:30:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260306_0006"
down_revision = "20260306_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "runtime_settings",
        sa.Column(
            "value_type",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'string'"),
        ),
    )
    op.add_column(
        "runtime_settings",
        sa.Column(
            "value",
            sa.Text(),
            nullable=False,
            server_default=sa.text("''"),
        ),
    )

    op.execute(
        sa.text(
            """
            UPDATE runtime_settings
            SET value_type = 'int',
                value = int_value::text
            WHERE int_value IS NOT NULL
            """
        )
    )

    with op.batch_alter_table("runtime_settings") as batch_op:
        batch_op.drop_column("int_value")
        batch_op.alter_column("value_type", server_default=None)
        batch_op.alter_column("value", server_default=None)


def downgrade() -> None:
    with op.batch_alter_table("runtime_settings") as batch_op:
        batch_op.add_column(sa.Column("int_value", sa.Integer(), nullable=True))

    op.execute(
        sa.text(
            """
            UPDATE runtime_settings
            SET int_value = CASE
                WHEN value_type = 'int' AND value ~ '^-?[0-9]+$' THEN value::integer
                ELSE NULL
            END
            """
        )
    )

    with op.batch_alter_table("runtime_settings") as batch_op:
        batch_op.drop_column("value")
        batch_op.drop_column("value_type")
