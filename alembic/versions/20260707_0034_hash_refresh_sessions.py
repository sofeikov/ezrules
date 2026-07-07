"""Hash stored refresh session tokens.

Revision ID: 20260707_0034
Revises: 20260630_0033
Create Date: 2026-07-07
"""

from __future__ import annotations

import hashlib
import string
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260707_0034"
down_revision: str | None = "20260630_0033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _is_sha256_hex(value: str) -> bool:
    return len(value) == 64 and all(char in string.hexdigits for char in value)


def upgrade() -> None:
    connection = op.get_bind()
    session_rows = connection.execute(sa.text("SELECT id, refresh_token FROM user_session")).mappings().all()

    for row in session_rows:
        raw_value = row["refresh_token"]
        if _is_sha256_hex(raw_value):
            continue
        token_hash = hashlib.sha256(raw_value.encode("utf-8")).hexdigest()
        connection.execute(
            sa.text("UPDATE user_session SET refresh_token = :token_hash WHERE id = :session_id"),
            {"token_hash": token_hash, "session_id": row["id"]},
        )

    op.alter_column(
        "user_session",
        "refresh_token",
        existing_type=sa.String(length=2048),
        type_=sa.String(length=64),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "user_session",
        "refresh_token",
        existing_type=sa.String(length=64),
        type_=sa.String(length=2048),
        existing_nullable=False,
    )
