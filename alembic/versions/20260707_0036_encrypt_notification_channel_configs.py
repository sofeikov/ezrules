"""Encrypt notification channel configs.

Revision ID: 20260707_0036
Revises: 20260706_0035
Create Date: 2026-07-07
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from ezrules.core.notification_channel_config import (
    decrypt_notification_channel_config,
    encrypt_notification_channel_config,
)

revision: str = "20260707_0036"
down_revision: str | None = "20260706_0035"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("notification_channels", sa.Column("config_encrypted", sa.Text(), nullable=True))

    connection = op.get_bind()
    rows = connection.execute(sa.text("SELECT nc_id, channel_type, config FROM notification_channels")).mappings()
    for row in rows:
        encrypted_config = encrypt_notification_channel_config(str(row["channel_type"]), row["config"])
        connection.execute(
            sa.text("UPDATE notification_channels SET config_encrypted = :config_encrypted WHERE nc_id = :nc_id"),
            {"config_encrypted": encrypted_config, "nc_id": row["nc_id"]},
        )

    op.alter_column("notification_channels", "config_encrypted", nullable=False)
    op.drop_column("notification_channels", "config")


def downgrade() -> None:
    op.add_column("notification_channels", sa.Column("config", sa.JSON(), nullable=True))

    connection = op.get_bind()
    update_config = sa.text("UPDATE notification_channels SET config = :config WHERE nc_id = :nc_id").bindparams(
        sa.bindparam("config", type_=sa.JSON())
    )
    rows = connection.execute(
        sa.text("SELECT nc_id, channel_type, config_encrypted FROM notification_channels")
    ).mappings()
    for row in rows:
        config = decrypt_notification_channel_config(str(row["channel_type"]), row["config_encrypted"])
        connection.execute(update_config, {"config": config, "nc_id": row["nc_id"]})

    op.alter_column("notification_channels", "config", nullable=False)
    op.drop_column("notification_channels", "config_encrypted")
