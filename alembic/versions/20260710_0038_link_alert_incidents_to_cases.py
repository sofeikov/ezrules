"""Link alert incidents to the existing case review workflow.

Revision ID: 20260710_0038
Revises: 20260707_0037
Create Date: 2026-07-10
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260710_0038"
down_revision: str | None = "20260707_0037"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "alert_incidents",
        sa.Column("severity", sa.String(length=32), server_default="critical", nullable=False),
    )
    op.create_table(
        "alert_incident_cases",
        sa.Column("aic_id", sa.Integer(), nullable=False),
        sa.Column("o_id", sa.Integer(), nullable=False),
        sa.Column("alert_incident_id", sa.Integer(), nullable=False),
        sa.Column("case_id", sa.Integer(), nullable=False),
        sa.Column("evaluation_decision_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["alert_incident_id"], ["alert_incidents.ai_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["case_id"], ["cases.case_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["evaluation_decision_id"], ["evaluation_decisions.ed_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["o_id"], ["organisation.o_id"]),
        sa.PrimaryKeyConstraint("aic_id"),
        sa.UniqueConstraint("aic_id"),
        sa.UniqueConstraint(
            "alert_incident_id",
            "evaluation_decision_id",
            name="uq_alert_incident_cases_incident_decision",
        ),
    )
    op.create_index("ix_alert_incident_cases_o_id_case", "alert_incident_cases", ["o_id", "case_id"])
    op.create_index("ix_alert_incident_cases_incident", "alert_incident_cases", ["alert_incident_id"])


def downgrade() -> None:
    op.drop_index("ix_alert_incident_cases_incident", table_name="alert_incident_cases")
    op.drop_index("ix_alert_incident_cases_o_id_case", table_name="alert_incident_cases")
    op.drop_table("alert_incident_cases")
    op.drop_column("alert_incidents", "severity")
