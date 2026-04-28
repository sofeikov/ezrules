"""
FastAPI routes for viewing recently tested events and triggered rules.
"""

from collections import defaultdict
from typing import Any

from fastapi import APIRouter, Depends, Query

from ezrules.backend.api_v2.auth.dependencies import (
    get_current_active_user,
    get_current_org_id,
    get_db,
    require_permission,
)
from ezrules.backend.api_v2.schemas.tested_events import TestedEventItem, TestedEventsResponse, TriggeredRuleItem
from ezrules.core.permissions_constants import PermissionAction
from ezrules.core.rule import Rule as ParsedRule
from ezrules.models.backend_core import (
    EvaluationDecision,
    EvaluationRuleResult,
    EventVersion,
    EventVersionLabel,
    Label,
    Rule,
    User,
)

router = APIRouter(prefix="/api/v2/tested-events", tags=["Tested Events"])


def _extract_referenced_fields(rule_logic: str) -> list[str]:
    """Extract top-level event fields referenced by a rule."""
    try:
        parsed_rule = ParsedRule(rid="", logic=rule_logic)
        return sorted(str(param) for param in parsed_rule.get_rule_params())
    except Exception:
        return []


@router.get("", response_model=TestedEventsResponse, response_model_exclude_unset=True)
def list_tested_events(
    limit: int = Query(default=50, ge=1, le=200, description="Max events to return"),
    include_referenced_fields: bool = Query(
        default=False,
        description="Include top-level event fields referenced by each triggered rule",
    ),
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.VIEW_RULES)),
    current_org_id: int = Depends(get_current_org_id),
    db: Any = Depends(get_db),
) -> TestedEventsResponse:
    """Return the most recently stored event evaluations with triggered rules."""
    records = (
        db.query(EvaluationDecision, EventVersion, Label.label)
        .join(EventVersion, EventVersion.ev_id == EvaluationDecision.ev_id)
        .outerjoin(EventVersionLabel, EventVersionLabel.ev_id == EvaluationDecision.ev_id)
        .outerjoin(Label, Label.el_id == EventVersionLabel.el_id)
        .filter(
            EvaluationDecision.o_id == current_org_id,
            EvaluationDecision.served.is_(True),
            EvaluationDecision.decision_type == "served",
        )
        .order_by(EvaluationDecision.ed_id.desc())
        .limit(limit)
        .all()
    )
    total = (
        db.query(EvaluationDecision)
        .filter(
            EvaluationDecision.o_id == current_org_id,
            EvaluationDecision.served.is_(True),
            EvaluationDecision.decision_type == "served",
        )
        .count()
    )

    triggered_rules_by_decision: dict[int, list[TriggeredRuleItem]] = defaultdict(list)
    referenced_fields_by_rule_id: dict[int, list[str]] = {}
    decision_ids = [int(decision.ed_id) for decision, _event_version, _label_name in records]

    if decision_ids:
        rule_rows = (
            db.query(
                EvaluationDecision.ed_id,
                Rule.r_id,
                Rule.rid,
                Rule.description,
                Rule.logic,
                EvaluationRuleResult.rule_result,
            )
            .join(EvaluationRuleResult, EvaluationRuleResult.ed_id == EvaluationDecision.ed_id)
            .join(Rule, Rule.r_id == EvaluationRuleResult.r_id)
            .filter(EvaluationDecision.ed_id.in_(decision_ids))
            .order_by(EvaluationDecision.ed_id.desc(), Rule.rid.asc())
            .all()
        )

        for ed_id, r_id, rid, description, rule_logic, rule_result in rule_rows:
            rule_id = int(r_id)
            if include_referenced_fields and rule_id not in referenced_fields_by_rule_id:
                referenced_fields_by_rule_id[rule_id] = _extract_referenced_fields(str(rule_logic))

            triggered_rule = TriggeredRuleItem(
                r_id=rule_id,
                rid=str(rid),
                description=str(description),
                outcome=str(rule_result),
            )
            if include_referenced_fields:
                triggered_rule.referenced_fields = referenced_fields_by_rule_id[rule_id]
            triggered_rules_by_decision[int(ed_id)].append(triggered_rule)

    events = [
        TestedEventItem(
            tl_id=int(decision.ed_id),
            event_id=str(decision.event_id),
            event_timestamp=int(decision.event_timestamp),
            resolved_outcome=str(decision.resolved_outcome) if decision.resolved_outcome is not None else None,
            label_name=str(label_name) if label_name is not None else None,
            outcome_counters=dict(decision.outcome_counters or {}),
            event_data=dict(event_version.event_data or {}),
            triggered_rules=triggered_rules_by_decision.get(int(decision.ed_id), []),
        )
        for decision, event_version, label_name in records
    ]

    return TestedEventsResponse(events=events, total=int(total), limit=limit)
