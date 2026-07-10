from datetime import UTC, date, datetime, time
from typing import Any, cast
from urllib.parse import urlparse

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query, status

from ezrules.backend.api_v2.auth.dependencies import (
    get_current_active_user,
    get_current_org_id,
    get_db,
    require_permission,
)
from ezrules.backend.api_v2.schemas.cases import (
    CaseAlertEvidenceResponse,
    CaseAssigneeResponse,
    CaseAssigneesResponse,
    CaseDetailResponse,
    CaseEvaluationResponse,
    CaseEventMutationResponse,
    CaseEventResponse,
    CaseListResponse,
    CaseMutationResponse,
    CaseNoteRequest,
    CaseResolveRequest,
    CaseResponse,
    CaseUpdateRequest,
    IntegrationEventResponse,
    IntegrationEventsResponse,
    IntegrationSubscriptionCreate,
    IntegrationSubscriptionMutationResponse,
    IntegrationSubscriptionResponse,
    IntegrationSubscriptionsResponse,
    IntegrationSubscriptionUpdate,
)
from ezrules.backend.api_v2.schemas.tested_events import TriggeredRuleItem
from ezrules.backend.cases import (
    CaseConflictError,
    CaseNotFoundError,
    CaseValidationError,
    add_case_note,
    assign_case,
    resolve_case,
)
from ezrules.backend.integrations import list_integration_events
from ezrules.core.permissions_constants import PermissionAction
from ezrules.models.backend_core import (
    AlertIncident,
    AlertIncidentCase,
    AlertRule,
    Case,
    CaseEvent,
    EvaluationDecision,
    EvaluationRuleResult,
    EventVersion,
    IntegrationEvent,
    IntegrationSubscription,
    Rule,
    User,
)

router = APIRouter(prefix="/api/v2", tags=["Cases"])
RULE_METADATA_SOURCE_CURRENT_FALLBACK = "current_rule_fallback"
RULE_METADATA_SOURCE_UNAVAILABLE = "unavailable"


def _validate_subscription_config(*, destination_type: str, config: dict[str, Any]) -> None:
    if destination_type.strip().lower() != "webhook":
        return

    url = str(config.get("url") or "").strip()
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Webhook subscriptions require config.url to be an HTTPS URL.",
        )


def _parse_case_filter_datetime(raw_value: str | None, *, param_name: str, end_of_day: bool = False) -> datetime | None:
    if not raw_value:
        return None

    value = raw_value.strip()
    if not value:
        return None

    try:
        if len(value) == 10:
            parsed_date = date.fromisoformat(value)
            boundary = time.max if end_of_day else time.min
            return datetime.combine(parsed_date, boundary, tzinfo=UTC)
        parsed_datetime = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{param_name} must be an ISO date or datetime.",
        ) from exc

    if parsed_datetime.tzinfo is None:
        return parsed_datetime.replace(tzinfo=UTC)
    return parsed_datetime


def _case_to_response(case: Case, user_emails_by_id: dict[int, str] | None = None) -> CaseResponse:
    user_emails_by_id = user_emails_by_id or {}
    assigned_to_user_id = int(case.assigned_to_user_id) if case.assigned_to_user_id is not None else None
    resolved_by_user_id = int(case.resolved_by_user_id) if case.resolved_by_user_id is not None else None
    return CaseResponse(
        id=int(case.case_id),
        transaction_id=str(case.transaction_id),
        current_event_version_id=int(case.current_ev_id),
        current_evaluation_decision_id=int(case.current_ed_id),
        opened_by_evaluation_decision_id=int(case.opened_by_ed_id),
        previous_evaluation_decision_id=int(case.previous_ed_id) if case.previous_ed_id is not None else None,
        resolved_outcome=str(case.resolved_outcome) if case.resolved_outcome else None,
        previous_resolved_outcome=str(case.previous_resolved_outcome) if case.previous_resolved_outcome else None,
        status=str(case.status),
        decision_state=str(case.decision_state),
        priority=int(case.priority),
        assigned_to_user_id=assigned_to_user_id,
        assigned_to_email=user_emails_by_id.get(assigned_to_user_id) if assigned_to_user_id is not None else None,
        resolved_by_user_id=resolved_by_user_id,
        resolved_by_email=user_emails_by_id.get(resolved_by_user_id) if resolved_by_user_id is not None else None,
        resolution_disposition=str(case.resolution_disposition) if case.resolution_disposition else None,
        resolution_action=str(case.resolution_action) if case.resolution_action else None,
        resolution_note=str(case.resolution_note) if case.resolution_note else None,
        resolution_label_id=int(case.resolution_label_id) if case.resolution_label_id is not None else None,
        reopened_from_case_id=int(case.reopened_from_case_id) if case.reopened_from_case_id is not None else None,
        created_at=case.created_at,  # type: ignore[arg-type]
        updated_at=case.updated_at,  # type: ignore[arg-type]
        resolved_at=case.resolved_at if case.resolved_at else None,  # type: ignore[arg-type]
    )


def _user_emails_for_cases(db: Any, *, cases: list[Case], current_org_id: int) -> dict[int, str]:
    user_ids = {
        int(user_id)
        for case in cases
        for user_id in (case.assigned_to_user_id, case.resolved_by_user_id)
        if user_id is not None
    }
    if not user_ids:
        return {}
    return {
        int(user.id): str(user.email)
        for user in db.query(User).filter(User.o_id == current_org_id, User.id.in_(sorted(user_ids))).all()
    }


def _case_event_to_response(event: CaseEvent) -> CaseEventResponse:
    return CaseEventResponse(
        id=int(event.case_event_id),
        case_id=int(event.case_id),
        event_type=str(event.event_type),
        actor_user_id=int(event.actor_user_id) if event.actor_user_id is not None else None,
        source_ed_id=int(event.source_ed_id) if event.source_ed_id is not None else None,
        external_event_id=str(event.external_event_id),
        occurred_at=event.occurred_at,  # type: ignore[arg-type]
        details=event.details if isinstance(event.details, dict) else {},
        created_at=event.created_at,  # type: ignore[arg-type]
    )


def _triggered_rule_response(
    *,
    r_id: int,
    outcome: Any,
    rule: Rule | None,
    snapshot_rid: str | None = None,
    snapshot_description: str | None = None,
    snapshot_referenced_fields: list[Any] | None = None,
    metadata_source: str | None = None,
) -> TriggeredRuleItem:
    if snapshot_rid is not None or snapshot_description is not None or snapshot_referenced_fields is not None:
        fallback_rid = str(rule.rid) if rule is not None else f"rule-{r_id}"
        fallback_description = str(rule.description) if rule is not None else ""
        rid = str(snapshot_rid or fallback_rid)
        description = str(snapshot_description or fallback_description)
        source = str(metadata_source or "evaluation_snapshot")
        referenced_fields = sorted(str(field) for field in (snapshot_referenced_fields or []))
    elif rule is not None:
        rid = str(rule.rid)
        description = str(rule.description)
        source = RULE_METADATA_SOURCE_CURRENT_FALLBACK
        referenced_fields = None
    else:
        rid = f"rule-{r_id}"
        description = "Rule metadata unavailable"
        source = RULE_METADATA_SOURCE_UNAVAILABLE
        referenced_fields = None

    return TriggeredRuleItem(
        r_id=r_id,
        rid=rid,
        description=description,
        outcome=str(outcome),
        metadata_source=source,
        referenced_fields=referenced_fields,
    )


def _case_evaluation_to_response(db: Any, *, current_org_id: int, case: Case) -> CaseEvaluationResponse | None:
    decision = (
        db.query(EvaluationDecision)
        .filter(EvaluationDecision.o_id == current_org_id, EvaluationDecision.ed_id == case.current_ed_id)
        .first()
    )
    event_version = (
        db.query(EventVersion)
        .filter(EventVersion.o_id == current_org_id, EventVersion.ev_id == case.current_ev_id)
        .first()
    )
    if decision is None or event_version is None:
        return None

    triggered_rules: list[TriggeredRuleItem] = []
    seen_rule_ids: set[int] = set()
    rule_result_rows = (
        db.query(EvaluationRuleResult, Rule)
        .outerjoin(Rule, Rule.r_id == EvaluationRuleResult.r_id)
        .filter(EvaluationRuleResult.ed_id == decision.ed_id)
        .order_by(EvaluationRuleResult.r_id.asc())
        .all()
    )
    for rule_result, rule in rule_result_rows:
        rule_id = int(rule_result.r_id)
        seen_rule_ids.add(rule_id)
        referenced_fields = rule_result.referenced_fields if isinstance(rule_result.referenced_fields, list) else None
        triggered_rules.append(
            _triggered_rule_response(
                r_id=rule_id,
                outcome=rule_result.rule_result,
                rule=rule,
                snapshot_rid=rule_result.rule_rid,
                snapshot_description=rule_result.rule_description,
                snapshot_referenced_fields=referenced_fields,
                metadata_source=rule_result.metadata_source,
            )
        )

    all_rule_results = dict(cast(dict[Any, Any], decision.all_rule_results or {}))
    missing_rule_results = [
        (int(rule_id), outcome)
        for rule_id, outcome in all_rule_results.items()
        if str(rule_id).isdigit() and outcome is not None and int(rule_id) not in seen_rule_ids
    ]
    rules_by_id = {}
    if missing_rule_results:
        rules_by_id = {
            int(rule.r_id): rule
            for rule in db.query(Rule)
            .filter(Rule.o_id == current_org_id, Rule.r_id.in_([rule_id for rule_id, _outcome in missing_rule_results]))
            .all()
        }
    for rule_id, outcome in missing_rule_results:
        triggered_rules.append(
            _triggered_rule_response(
                r_id=rule_id,
                outcome=outcome,
                rule=rules_by_id.get(rule_id),
            )
        )

    return CaseEvaluationResponse(
        evaluation_decision_id=int(decision.ed_id),
        transaction_id=str(decision.transaction_id),
        event_version_id=int(event_version.ev_id),
        event_version=int(decision.event_version),
        effective_at=decision.effective_at,  # type: ignore[arg-type]
        observed_at=decision.observed_at,  # type: ignore[arg-type]
        evaluated_at=decision.evaluated_at,  # type: ignore[arg-type]
        is_current=bool(decision.is_current),
        resolved_outcome=str(decision.resolved_outcome) if decision.resolved_outcome is not None else None,
        outcome_counters=dict(cast(dict[str, int], decision.outcome_counters or {})),
        event_data=dict(cast(dict[str, Any], event_version.event_data or {})),
        triggered_rules=triggered_rules,
    )


def _integration_event_to_response(event: IntegrationEvent) -> IntegrationEventResponse:
    return IntegrationEventResponse(
        id=int(event.integration_event_id),
        external_event_id=str(event.external_event_id),
        source_type=str(event.source_type),
        source_id=int(event.source_id),
        event_type=str(event.event_type),
        event_version=int(event.event_version),
        occurred_at=event.occurred_at,  # type: ignore[arg-type]
        payload=event.payload if isinstance(event.payload, dict) else {},
        created_at=event.created_at,  # type: ignore[arg-type]
    )


def _subscription_to_response(subscription: IntegrationSubscription) -> IntegrationSubscriptionResponse:
    event_types = subscription.event_types if isinstance(subscription.event_types, list) else []
    config = dict(subscription.config) if isinstance(subscription.config, dict) else {}
    config.pop("secret", None)
    return IntegrationSubscriptionResponse(
        id=int(subscription.subscription_id),
        name=str(subscription.name),
        destination_type=str(subscription.destination_type),
        config=config,
        event_types=[str(event_type) for event_type in event_types],
        enabled=bool(subscription.enabled),
        created_at=subscription.created_at,  # type: ignore[arg-type]
        updated_at=subscription.updated_at,  # type: ignore[arg-type]
    )


@router.get("/cases", response_model=CaseListResponse)
def list_cases(
    status_filter: str | None = Query(default=None, alias="status"),
    outcome: str | None = None,
    assigned_to: str | None = None,
    priority_min: int | None = Query(default=None, ge=0),
    decision_state: str | None = None,
    transaction_id: str | None = None,
    q: str | None = None,
    created_from: str | None = None,
    created_to: str | None = None,
    updated_from: str | None = None,
    updated_to: str | None = None,
    alert_incident_id: int | None = Query(default=None, ge=1),
    alert_rule_id: int | None = Query(default=None, ge=1),
    alert_severity: str | None = None,
    alerted_from: str | None = None,
    alerted_to: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.VIEW_CASES)),
    current_org_id: int = Depends(get_current_org_id),
    db: Any = Depends(get_db),
) -> CaseListResponse:
    query = db.query(Case).filter(Case.o_id == current_org_id)
    alert_filter_requested = any(
        value is not None for value in (alert_incident_id, alert_rule_id, alert_severity, alerted_from, alerted_to)
    )
    if alert_filter_requested:
        query = query.join(AlertIncidentCase, AlertIncidentCase.case_id == Case.case_id).join(
            AlertIncident, AlertIncident.ai_id == AlertIncidentCase.alert_incident_id
        )
        if alert_incident_id is not None:
            query = query.filter(AlertIncident.ai_id == alert_incident_id)
        if alert_rule_id is not None:
            query = query.filter(AlertIncident.alert_rule_id == alert_rule_id)
        if alert_severity:
            query = query.filter(sa.func.lower(AlertIncident.severity) == alert_severity.strip().lower())
        alerted_from_value = _parse_case_filter_datetime(alerted_from, param_name="alerted_from")
        alerted_to_value = _parse_case_filter_datetime(alerted_to, param_name="alerted_to", end_of_day=True)
        if alerted_from_value is not None:
            query = query.filter(AlertIncident.triggered_at >= alerted_from_value)
        if alerted_to_value is not None:
            query = query.filter(AlertIncident.triggered_at <= alerted_to_value)
        query = query.distinct()
    if status_filter:
        query = query.filter(Case.status == status_filter)
    if outcome:
        query = query.filter(sa.func.upper(Case.resolved_outcome) == outcome.strip().upper())
    if assigned_to:
        normalized_assigned_to = assigned_to.strip().lower()
        if normalized_assigned_to in {"me", "assigned_to_me"}:
            query = query.filter(Case.assigned_to_user_id == int(user.id))
        elif normalized_assigned_to in {"none", "unassigned"}:
            query = query.filter(Case.assigned_to_user_id.is_(None))
        elif normalized_assigned_to.isdigit():
            query = query.filter(Case.assigned_to_user_id == int(normalized_assigned_to))
        else:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="assigned_to must be 'me', 'unassigned', or a user id.",
            )
    if priority_min is not None:
        query = query.filter(Case.priority >= priority_min)
    if decision_state:
        query = query.filter(Case.decision_state == decision_state.strip())
    if transaction_id:
        query = query.filter(Case.transaction_id == transaction_id.strip())
    if q:
        query = query.filter(Case.transaction_id.ilike(f"%{q.strip()}%"))
    created_from_value = _parse_case_filter_datetime(created_from, param_name="created_from")
    created_to_value = _parse_case_filter_datetime(created_to, param_name="created_to", end_of_day=True)
    updated_from_value = _parse_case_filter_datetime(updated_from, param_name="updated_from")
    updated_to_value = _parse_case_filter_datetime(updated_to, param_name="updated_to", end_of_day=True)
    if created_from_value is not None:
        query = query.filter(Case.created_at >= created_from_value)
    if created_to_value is not None:
        query = query.filter(Case.created_at <= created_to_value)
    if updated_from_value is not None:
        query = query.filter(Case.updated_at >= updated_from_value)
    if updated_to_value is not None:
        query = query.filter(Case.updated_at <= updated_to_value)
    total = int(query.count())
    cases = query.order_by(Case.updated_at.desc(), Case.case_id.desc()).offset(offset).limit(limit).all()
    user_emails = _user_emails_for_cases(db, cases=cases, current_org_id=current_org_id)
    return CaseListResponse(cases=[_case_to_response(case, user_emails) for case in cases], total=total)


@router.get("/cases/assignees", response_model=CaseAssigneesResponse)
def list_case_assignees(
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.VIEW_CASES)),
    current_org_id: int = Depends(get_current_org_id),
    db: Any = Depends(get_db),
) -> CaseAssigneesResponse:
    users = db.query(User).filter(User.o_id == current_org_id, User.active.is_(True)).order_by(User.email.asc()).all()
    return CaseAssigneesResponse(users=[CaseAssigneeResponse(id=int(item.id), email=str(item.email)) for item in users])


@router.get("/cases/{case_id}", response_model=CaseDetailResponse)
def get_case(
    case_id: int,
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.VIEW_CASES)),
    current_org_id: int = Depends(get_current_org_id),
    db: Any = Depends(get_db),
) -> CaseDetailResponse:
    case = db.query(Case).filter(Case.o_id == current_org_id, Case.case_id == case_id).first()
    if case is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
    events = (
        db.query(CaseEvent)
        .filter(CaseEvent.o_id == current_org_id, CaseEvent.case_id == case_id)
        .order_by(CaseEvent.created_at.asc(), CaseEvent.case_event_id.asc())
        .all()
    )
    user_emails = _user_emails_for_cases(db, cases=[case], current_org_id=current_org_id)
    alert_rows = (
        db.query(AlertIncidentCase, AlertIncident, AlertRule)
        .join(AlertIncident, AlertIncident.ai_id == AlertIncidentCase.alert_incident_id)
        .join(AlertRule, AlertRule.ar_id == AlertIncident.alert_rule_id)
        .filter(AlertIncidentCase.o_id == current_org_id, AlertIncidentCase.case_id == case_id)
        .order_by(AlertIncident.triggered_at.desc(), AlertIncident.ai_id.desc())
        .all()
    )
    return CaseDetailResponse(
        case=_case_to_response(case, user_emails),
        events=[_case_event_to_response(event) for event in events],
        evaluation=_case_evaluation_to_response(db, current_org_id=current_org_id, case=case),
        alerts=[
            CaseAlertEvidenceResponse(
                incident_id=int(incident.ai_id),
                alert_rule_id=int(rule.ar_id),
                alert_rule_name=str(rule.name),
                evaluation_decision_id=int(link.evaluation_decision_id),
                outcome=str(incident.outcome),
                severity=str(incident.severity),
                observed_count=int(incident.observed_count),
                threshold=int(incident.threshold),
                window_start=incident.window_start,
                window_end=incident.window_end,
                triggered_at=incident.triggered_at,
            )
            for link, incident, rule in alert_rows
        ],
    )


@router.patch("/cases/{case_id}", response_model=CaseMutationResponse)
def update_case(
    case_id: int,
    payload: CaseUpdateRequest,
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.MANAGE_CASES)),
    current_org_id: int = Depends(get_current_org_id),
    db: Any = Depends(get_db),
) -> CaseMutationResponse:
    if "assigned_to_user_id" not in payload.model_fields_set:
        case = db.query(Case).filter(Case.o_id == current_org_id, Case.case_id == case_id).first()
        if case is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
        user_emails = _user_emails_for_cases(db, cases=[case], current_org_id=current_org_id)
        return CaseMutationResponse(success=True, message="Case unchanged", case=_case_to_response(case, user_emails))

    try:
        case = assign_case(
            db,
            o_id=current_org_id,
            case_id=case_id,
            actor_user_id=int(user.id),
            assignee_user_id=payload.assigned_to_user_id,
        )
    except CaseNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found") from exc
    except CaseValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    db.commit()
    user_emails = _user_emails_for_cases(db, cases=[case], current_org_id=current_org_id)
    return CaseMutationResponse(success=True, message="Case updated", case=_case_to_response(case, user_emails))


@router.post("/cases/{case_id}/notes", response_model=CaseEventMutationResponse, status_code=status.HTTP_201_CREATED)
def add_case_note_route(
    case_id: int,
    payload: CaseNoteRequest,
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.MANAGE_CASES)),
    current_org_id: int = Depends(get_current_org_id),
    db: Any = Depends(get_db),
) -> CaseEventMutationResponse:
    try:
        event = add_case_note(
            db,
            o_id=current_org_id,
            case_id=case_id,
            actor_user_id=int(user.id),
            note=payload.note,
        )
    except CaseNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found") from exc
    db.commit()
    return CaseEventMutationResponse(success=True, message="Case note added", event=_case_event_to_response(event))


@router.post("/cases/{case_id}/resolve", response_model=CaseMutationResponse)
def resolve_case_route(
    case_id: int,
    payload: CaseResolveRequest,
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.MANAGE_CASES)),
    current_org_id: int = Depends(get_current_org_id),
    db: Any = Depends(get_db),
) -> CaseMutationResponse:
    try:
        case = resolve_case(
            db,
            o_id=current_org_id,
            case_id=case_id,
            actor_user_id=int(user.id),
            resolution_disposition=payload.resolution_disposition,
            resolution_action=payload.resolution_action,
            resolution_note=payload.resolution_note,
            resolution_label_id=payload.resolution_label_id,
            expected_current_ed_id=payload.expected_current_ed_id,
        )
    except CaseNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found") from exc
    except CaseConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except CaseValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    db.commit()
    user_emails = _user_emails_for_cases(db, cases=[case], current_org_id=current_org_id)
    return CaseMutationResponse(success=True, message="Case resolved", case=_case_to_response(case, user_emails))


@router.get("/integration-events", response_model=IntegrationEventsResponse)
def list_events(
    cursor: int | None = Query(default=None, ge=1),
    event_type: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.VIEW_INTEGRATIONS)),
    current_org_id: int = Depends(get_current_org_id),
    db: Any = Depends(get_db),
) -> IntegrationEventsResponse:
    events = list_integration_events(db, o_id=current_org_id, after_id=cursor, event_type=event_type, limit=limit)
    next_cursor = int(events[-1].integration_event_id) if len(events) == limit else None
    return IntegrationEventsResponse(
        events=[_integration_event_to_response(event) for event in events], next_cursor=next_cursor
    )


@router.get("/integration-subscriptions", response_model=IntegrationSubscriptionsResponse)
def list_subscriptions(
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.VIEW_INTEGRATIONS)),
    current_org_id: int = Depends(get_current_org_id),
    db: Any = Depends(get_db),
) -> IntegrationSubscriptionsResponse:
    subscriptions = (
        db.query(IntegrationSubscription)
        .filter(IntegrationSubscription.o_id == current_org_id)
        .order_by(IntegrationSubscription.created_at.desc(), IntegrationSubscription.subscription_id.desc())
        .all()
    )
    return IntegrationSubscriptionsResponse(subscriptions=[_subscription_to_response(item) for item in subscriptions])


@router.post(
    "/integration-subscriptions",
    response_model=IntegrationSubscriptionMutationResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_subscription(
    payload: IntegrationSubscriptionCreate,
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.MANAGE_INTEGRATIONS)),
    current_org_id: int = Depends(get_current_org_id),
    db: Any = Depends(get_db),
) -> IntegrationSubscriptionMutationResponse:
    now = datetime.now(UTC)
    destination_type = payload.destination_type.strip().lower()
    config = dict(payload.config)
    _validate_subscription_config(destination_type=destination_type, config=config)
    subscription = IntegrationSubscription(
        o_id=current_org_id,
        name=payload.name.strip(),
        destination_type=destination_type,
        config=config,
        event_types=payload.event_types,
        enabled=payload.enabled,
        created_at=now,
        updated_at=now,
    )
    db.add(subscription)
    db.commit()
    return IntegrationSubscriptionMutationResponse(
        success=True,
        message="Integration subscription created",
        subscription=_subscription_to_response(subscription),
    )


@router.patch("/integration-subscriptions/{subscription_id}", response_model=IntegrationSubscriptionMutationResponse)
def update_subscription(
    subscription_id: int,
    payload: IntegrationSubscriptionUpdate,
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.MANAGE_INTEGRATIONS)),
    current_org_id: int = Depends(get_current_org_id),
    db: Any = Depends(get_db),
) -> IntegrationSubscriptionMutationResponse:
    subscription = (
        db.query(IntegrationSubscription)
        .filter(
            IntegrationSubscription.o_id == current_org_id, IntegrationSubscription.subscription_id == subscription_id
        )
        .first()
    )
    if subscription is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Integration subscription not found")
    destination_type = (
        payload.destination_type.strip().lower()
        if payload.destination_type is not None
        else str(subscription.destination_type)
    )
    config = dict(subscription.config or {})
    if payload.config is not None:
        config.update(payload.config)
    _validate_subscription_config(destination_type=destination_type, config=config)
    if payload.name is not None:
        subscription.name = payload.name.strip()
    if payload.destination_type is not None:
        subscription.destination_type = destination_type
    if payload.config is not None:
        subscription.config = config
    if payload.event_types is not None:
        subscription.event_types = payload.event_types
    if payload.enabled is not None:
        subscription.enabled = payload.enabled
    subscription.updated_at = datetime.now(UTC)
    db.commit()
    return IntegrationSubscriptionMutationResponse(
        success=True,
        message="Integration subscription updated",
        subscription=_subscription_to_response(subscription),
    )
