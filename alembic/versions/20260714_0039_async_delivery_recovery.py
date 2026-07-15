"""Make asynchronous shadow delivery idempotent.

Revision ID: 20260714_0039
Revises: 20260710_0038
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260714_0039"
down_revision: str | None = "20260710_0038"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_shadow_results_log_ed_rule",
        "shadow_results_log",
        ["ed_id", "r_id"],
    )
    op.create_unique_constraint(
        "uq_rule_deployment_results_log_ed_rule_mode",
        "rule_deployment_results_log",
        ["ed_id", "r_id", "mode"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_rule_deployment_results_log_ed_rule_mode",
        "rule_deployment_results_log",
        type_="unique",
    )
    op.drop_constraint(
        "uq_shadow_results_log_ed_rule",
        "shadow_results_log",
        type_="unique",
    )
