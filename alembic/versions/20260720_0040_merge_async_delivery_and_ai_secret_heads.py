"""Merge asynchronous delivery and AI secret migration heads.

Revision ID: 20260720_0040
Revises: 20260713_0039, 20260714_0039
Create Date: 2026-07-20
"""

from collections.abc import Sequence

revision: str = "20260720_0040"
down_revision: str | Sequence[str] | None = ("20260713_0039", "20260714_0039")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
