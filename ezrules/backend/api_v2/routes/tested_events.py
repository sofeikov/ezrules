"""
FastAPI routes for viewing recently tested events and triggered rules.
"""

from collections import defaultdict
from typing import Any

from fastapi import APIRouter, Depends, Query

from ezrules.backend.api_v2.auth.dependencies import (
    get_current_active_user,
    get_db,
    require_permission,
)
from ezrules.backend.api_v2.schemas.tested_events import TestedEventItem, TestedEventsResponse, TriggeredRuleItem
from ezrules.core.permissions_constants import PermissionAction
from ezrules.models.backend_core import Rule, TestingRecordLog, TestingResultsLog, User
from ezrules.settings import app_settings

router = APIRouter(prefix="/api/v2/tested-events", tags=["Tested Events"])


@router.get("", response_model=TestedEventsResponse)
def list_tested_events(
    limit: int = Query(default=50, ge=1, le=200, description="Max events to return"),
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.VIEW_RULES)),
    db: Any = Depends(get_db),
) -> TestedEventsResponse:
    """Return the most recently stored event evaluations with triggered rules."""
    records = (
        db.query(TestingRecordLog)
        .filter(TestingRecordLog.o_id == app_settings.ORG_ID)
        .order_by(TestingRecordLog.tl_id.desc())
        .limit(limit)
        .all()
    )
    total = db.query(TestingRecordLog).filter(TestingRecordLog.o_id == app_settings.ORG_ID).count()

    triggered_rules_by_tl: dict[int, list[TriggeredRuleItem]] = defaultdict(list)
    record_ids = [int(record.tl_id) for record in records]

    if record_ids:
        rule_rows = (
            db.query(
                TestingResultsLog.tl_id,
                Rule.r_id,
                Rule.rid,
                Rule.description,
                TestingResultsLog.rule_result,
            )
            .join(Rule, Rule.r_id == TestingResultsLog.r_id)
            .filter(TestingResultsLog.tl_id.in_(record_ids))
            .order_by(TestingResultsLog.tl_id.desc(), Rule.rid.asc())
            .all()
        )

        for tl_id, r_id, rid, description, rule_result in rule_rows:
            triggered_rules_by_tl[int(tl_id)].append(
                TriggeredRuleItem(
                    r_id=int(r_id),
                    rid=str(rid),
                    description=str(description),
                    outcome=str(rule_result),
                )
            )

    events = [
        TestedEventItem(
            tl_id=int(record.tl_id),
            event_id=str(record.event_id),
            event_timestamp=int(record.event_timestamp),
            resolved_outcome=str(record.resolved_outcome) if record.resolved_outcome is not None else None,
            outcome_counters=dict(record.outcome_counters or {}),
            event_data=dict(record.event or {}),
            triggered_rules=triggered_rules_by_tl.get(int(record.tl_id), []),
        )
        for record in records
    ]

    return TestedEventsResponse(events=events, total=int(total), limit=limit)
