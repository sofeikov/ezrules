"""Bounded operational case metrics for the manager dashboard."""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from ezrules.backend.cases import ACTIVE_CASE_STATUSES
from ezrules.models.backend_core import Case, EvaluationDecision, EvaluationRuleResult, Rule, User

ATTENTION_CASE_LIMIT = 10
NOISY_RULE_LIMIT = 5


@dataclass(frozen=True, slots=True)
class OperationsPeriod:
    days: int
    start: datetime.datetime
    end: datetime.datetime
    generated_at: datetime.datetime


def _utc_datetime(value: datetime.datetime) -> datetime.datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=datetime.UTC)
    return value.astimezone(datetime.UTC)


def _rate(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return round(numerator / denominator, 4)


def build_operations_period(days: int, *, now: datetime.datetime | None = None) -> OperationsPeriod:
    generated_at = _utc_datetime(now or datetime.datetime.now(datetime.UTC))
    start_date = generated_at.date() - datetime.timedelta(days=days - 1)
    start = datetime.datetime.combine(start_date, datetime.time.min, tzinfo=datetime.UTC)
    return OperationsPeriod(days=days, start=start, end=generated_at, generated_at=generated_at)


def _case_flow(db: Any, *, o_id: int, period: OperationsPeriod) -> list[dict[str, Any]]:
    opened_day = sa.cast(Case.created_at, sa.Date)
    opened_rows = (
        db.query(opened_day.label("day"), sa.func.count(Case.case_id).label("count"))
        .filter(
            Case.o_id == o_id,
            Case.created_at >= period.start,
            Case.created_at < period.end,
        )
        .group_by(opened_day)
        .all()
    )
    resolved_day = sa.cast(Case.resolved_at, sa.Date)
    resolved_rows = (
        db.query(resolved_day.label("day"), sa.func.count(Case.case_id).label("count"))
        .filter(
            Case.o_id == o_id,
            Case.resolved_at >= period.start,
            Case.resolved_at < period.end,
        )
        .group_by(resolved_day)
        .all()
    )
    opened_counts = {row.day: int(row.count) for row in opened_rows}
    resolved_counts = {row.day: int(row.count) for row in resolved_rows}
    return [
        {
            "date": period.start.date() + datetime.timedelta(days=offset),
            "opened": opened_counts.get(period.start.date() + datetime.timedelta(days=offset), 0),
            "resolved": resolved_counts.get(period.start.date() + datetime.timedelta(days=offset), 0),
        }
        for offset in range(period.days)
    ]


def _attention_cases(db: Any, *, o_id: int, period: OperationsPeriod) -> list[dict[str, Any]]:
    rows = (
        db.query(Case, User.email.label("assignee_email"))
        .outerjoin(User, User.id == Case.assigned_to_user_id)
        .filter(Case.o_id == o_id, Case.status.in_(ACTIVE_CASE_STATUSES))
        .order_by(Case.priority.desc(), Case.created_at.asc(), Case.case_id.asc())
        .limit(ATTENTION_CASE_LIMIT)
        .all()
    )
    return [
        {
            "case_id": int(case.case_id),
            "outcome": str(case.resolved_outcome) if case.resolved_outcome else None,
            "assigned_to_email": str(assignee_email) if assignee_email else None,
            "age_seconds": max(
                0,
                int((period.generated_at - _utc_datetime(case.created_at)).total_seconds()),
            ),
        }
        for case, assignee_email in rows
    ]


def _noisy_rules(db: Any, *, o_id: int, period: OperationsPeriod) -> list[dict[str, Any]]:
    snapshot_pairs = (
        db.query(
            Case.case_id.label("case_id"),
            EvaluationRuleResult.r_id.label("rule_id"),
            sa.func.max(sa.func.coalesce(EvaluationRuleResult.rule_rid, Rule.rid)).label("rid"),
            sa.func.max(sa.func.coalesce(EvaluationRuleResult.rule_description, Rule.description)).label("description"),
            sa.func.max(Case.resolved_at).label("resolved_at"),
            sa.func.max(Case.resolution_disposition).label("resolution_disposition"),
        )
        .join(EvaluationRuleResult, EvaluationRuleResult.ed_id == Case.opened_by_ed_id)
        .join(EvaluationDecision, EvaluationDecision.ed_id == Case.opened_by_ed_id)
        .outerjoin(Rule, Rule.r_id == EvaluationRuleResult.r_id)
        .filter(
            Case.o_id == o_id,
            Case.created_at >= period.start,
            Case.created_at < period.end,
            EvaluationRuleResult.rule_result == EvaluationDecision.resolved_outcome,
        )
        .group_by(Case.case_id, EvaluationRuleResult.r_id)
    )

    raw_all_rule_results = sa.cast(EvaluationDecision.all_rule_results, JSONB)
    safe_all_rule_results = sa.case(
        (sa.func.jsonb_typeof(raw_all_rule_results) == "object", raw_all_rule_results),
        else_=sa.cast(sa.literal("{}"), JSONB),
    )
    expanded_results = sa.func.jsonb_each(safe_all_rule_results).table_valued("key", "value").lateral()
    expanded_rule_id = sa.cast(expanded_results.c.key, sa.Integer)
    deleted_rule_pairs = (
        db.query(
            Case.case_id.label("case_id"),
            expanded_rule_id.label("rule_id"),
            sa.func.coalesce(Rule.rid, sa.func.concat("rule_", expanded_results.c.key)).label("rid"),
            sa.func.coalesce(Rule.description, sa.literal("Deleted rule")).label("description"),
            Case.resolved_at.label("resolved_at"),
            Case.resolution_disposition.label("resolution_disposition"),
        )
        .join(EvaluationDecision, EvaluationDecision.ed_id == Case.opened_by_ed_id)
        .join(expanded_results, sa.true())
        .outerjoin(
            EvaluationRuleResult,
            sa.and_(
                EvaluationRuleResult.ed_id == EvaluationDecision.ed_id,
                EvaluationRuleResult.r_id == expanded_rule_id,
            ),
        )
        .outerjoin(Rule, Rule.r_id == expanded_rule_id)
        .filter(
            Case.o_id == o_id,
            Case.created_at >= period.start,
            Case.created_at < period.end,
            EvaluationRuleResult.err_id.is_(None),
            expanded_results.c.value == sa.func.to_jsonb(EvaluationDecision.resolved_outcome),
        )
    )
    case_rule_pairs = snapshot_pairs.union_all(deleted_rule_pairs).subquery()

    case_count = sa.func.count(case_rule_pairs.c.case_id)
    resolved_count = sa.func.sum(sa.case((case_rule_pairs.c.resolved_at.isnot(None), 1), else_=0))
    dispositioned_count = sa.func.sum(sa.case((case_rule_pairs.c.resolution_disposition.isnot(None), 1), else_=0))
    false_positive_count = sa.func.sum(
        sa.case((case_rule_pairs.c.resolution_disposition == "false_positive", 1), else_=0)
    )
    rows = (
        db.query(
            case_rule_pairs.c.rule_id,
            sa.func.max(case_rule_pairs.c.rid).label("rid"),
            sa.func.max(case_rule_pairs.c.description).label("description"),
            case_count.label("case_count"),
            resolved_count.label("resolved_count"),
            dispositioned_count.label("dispositioned_count"),
            false_positive_count.label("false_positive_count"),
        )
        .group_by(case_rule_pairs.c.rule_id)
        .order_by(case_count.desc(), sa.func.max(case_rule_pairs.c.rid).asc())
        .limit(NOISY_RULE_LIMIT)
        .all()
    )
    return [
        {
            "rid": str(row.rid or f"rule_{row.rule_id}"),
            "description": str(row.description or "Historical rule"),
            "case_count": int(row.case_count),
            "resolved_count": int(row.resolved_count or 0),
            "false_positive_count": int(row.false_positive_count or 0),
            "false_positive_rate": _rate(
                int(row.false_positive_count or 0),
                int(row.dispositioned_count or 0),
            ),
        }
        for row in rows
    ]


def build_operations_summary(
    db: Any,
    *,
    o_id: int,
    days: int,
    now: datetime.datetime | None = None,
) -> dict[str, Any]:
    """Return one bounded, org-scoped operational summary."""
    period = build_operations_period(days, now=now)
    active_filter = Case.status.in_(ACTIVE_CASE_STATUSES)
    active_cases = int(db.query(sa.func.count(Case.case_id)).filter(Case.o_id == o_id, active_filter).scalar() or 0)
    unassigned_cases = int(
        db.query(sa.func.count(Case.case_id))
        .filter(Case.o_id == o_id, active_filter, Case.assigned_to_user_id.is_(None))
        .scalar()
        or 0
    )
    resolved_cases = int(
        db.query(sa.func.count(Case.case_id))
        .filter(
            Case.o_id == o_id,
            Case.resolved_at >= period.start,
            Case.resolved_at < period.end,
        )
        .scalar()
        or 0
    )
    dispositioned_cases = int(
        db.query(sa.func.count(Case.case_id))
        .filter(
            Case.o_id == o_id,
            Case.resolved_at >= period.start,
            Case.resolved_at < period.end,
            Case.resolution_disposition.isnot(None),
        )
        .scalar()
        or 0
    )
    false_positive_cases = int(
        db.query(sa.func.count(Case.case_id))
        .filter(
            Case.o_id == o_id,
            Case.resolved_at >= period.start,
            Case.resolved_at < period.end,
            Case.resolution_disposition == "false_positive",
        )
        .scalar()
        or 0
    )
    return {
        "days": period.days,
        "period_start": period.start,
        "period_end": period.end,
        "generated_at": period.generated_at,
        "summary": {
            "active_cases": active_cases,
            "unassigned_cases": unassigned_cases,
            "resolved_cases": resolved_cases,
            "dispositioned_cases": dispositioned_cases,
            "false_positive_cases": false_positive_cases,
            "false_positive_rate": _rate(false_positive_cases, dispositioned_cases),
        },
        "case_flow": _case_flow(db, o_id=o_id, period=period),
        "attention_cases": _attention_cases(db, o_id=o_id, period=period),
        "noisy_rules": _noisy_rules(db, o_id=o_id, period=period),
    }
