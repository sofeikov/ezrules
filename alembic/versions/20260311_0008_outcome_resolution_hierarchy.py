"""Add outcome severity ordering and persisted resolved outcomes.

Revision ID: 20260311_0008
Revises: 20260306_0007
Create Date: 2026-03-11 12:00:00.000000
"""

from __future__ import annotations

from collections import defaultdict

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260311_0008"
down_revision = "20260306_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("allowed_outcomes", sa.Column("severity_rank", sa.Integer(), nullable=True))
    op.add_column("testing_record_log", sa.Column("outcome_counters", sa.JSON(), nullable=True))
    op.add_column("testing_record_log", sa.Column("resolved_outcome", sa.String(), nullable=True))

    conn = op.get_bind()
    rows = conn.execute(
        sa.text(
            """
            SELECT ao_id, outcome_name, o_id
            FROM allowed_outcomes
            ORDER BY o_id, ao_id
            """
        )
    ).mappings()

    outcomes_by_org: dict[int, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        outcomes_by_org[int(row["o_id"])].append(dict(row))

    preferred_order = ["CANCEL", "HOLD", "RELEASE"]

    for org_id, outcomes in outcomes_by_org.items():
        ordered: list[dict[str, object]] = []

        for outcome_name in preferred_order:
            ordered.extend(item for item in outcomes if item["outcome_name"] == outcome_name)

        ordered.extend(item for item in outcomes if item["outcome_name"] not in preferred_order)

        for severity_rank, item in enumerate(ordered, start=1):
            conn.execute(
                sa.text(
                    """
                    UPDATE allowed_outcomes
                    SET severity_rank = :severity_rank
                    WHERE ao_id = :ao_id AND o_id = :o_id
                    """
                ),
                {
                    "severity_rank": severity_rank,
                    "ao_id": int(item["ao_id"]),
                    "o_id": org_id,
                },
            )

    op.alter_column("allowed_outcomes", "severity_rank", nullable=False)
    op.create_unique_constraint(
        "uq_allowed_outcomes_org_severity_rank",
        "allowed_outcomes",
        ["o_id", "severity_rank"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_allowed_outcomes_org_severity_rank", "allowed_outcomes", type_="unique")
    with op.batch_alter_table("testing_record_log") as batch_op:
        batch_op.drop_column("resolved_outcome")
        batch_op.drop_column("outcome_counters")
    with op.batch_alter_table("allowed_outcomes") as batch_op:
        batch_op.drop_column("severity_rank")
