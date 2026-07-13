"""Encrypt AI authoring API keys.

Revision ID: 20260713_0039
Revises: 20260710_0038
Create Date: 2026-07-13
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from ezrules.core.secret_encryption import SECRET_ENCRYPTION_PREFIX, decrypt_secret, encrypt_secret
from ezrules.settings import app_settings

revision: str = "20260713_0039"
down_revision: str | None = "20260710_0038"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_AI_AUTHORING_API_KEY = "ai_authoring_api_key"
_ALEMBIC_PLACEHOLDER_SECRET = "alembic-placeholder-secret"


def upgrade() -> None:
    connection = op.get_bind()
    rows = list(
        connection.execute(
            sa.text("SELECT o_id, value FROM runtime_settings WHERE key = :key"),
            {"key": _AI_AUTHORING_API_KEY},
        ).mappings()
    )
    _require_real_app_secret(rows)

    for row in rows:
        connection.execute(
            sa.text(
                """
                UPDATE runtime_settings
                SET value = :value, value_type = 'secret'
                WHERE key = :key AND o_id = :o_id
                """
            ),
            {
                "key": _AI_AUTHORING_API_KEY,
                "o_id": row["o_id"],
                "value": _encrypt_legacy_value(str(row["value"])),
            },
        )


def downgrade() -> None:
    connection = op.get_bind()
    rows = list(
        connection.execute(
            sa.text("SELECT o_id, value FROM runtime_settings WHERE key = :key"),
            {"key": _AI_AUTHORING_API_KEY},
        ).mappings()
    )
    _require_real_app_secret(rows)

    for row in rows:
        connection.execute(
            sa.text(
                """
                UPDATE runtime_settings
                SET value = :value, value_type = 'string'
                WHERE key = :key AND o_id = :o_id
                """
            ),
            {
                "key": _AI_AUTHORING_API_KEY,
                "o_id": row["o_id"],
                "value": decrypt_secret(str(row["value"])),
            },
        )


def _require_real_app_secret(rows: Sequence[object]) -> None:
    if rows and app_settings.APP_SECRET == _ALEMBIC_PLACEHOLDER_SECRET:
        raise RuntimeError("EZRULES_APP_SECRET must be set to migrate stored AI authoring API keys")


def _encrypt_legacy_value(value: str) -> str:
    if value.startswith(SECRET_ENCRYPTION_PREFIX):
        decrypt_secret(value)
        return value
    return encrypt_secret(value)
