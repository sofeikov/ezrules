from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ezrules.backend.api_v2.auth.dependencies import (
    get_current_active_user,
    get_current_org_id,
    get_db,
    require_permission,
)
from ezrules.backend.api_v2.schemas.cases import (
    CaseDetailResponse,
    CaseEventResponse,
    CaseListResponse,
    CaseMutationResponse,
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
from ezrules.backend.cases import CaseConflictError, CaseNotFoundError, CaseValidationError, assign_case, resolve_case
from ezrules.backend.integrations import list_integration_events
from ezrules.core.permissions_constants import PermissionAction
from ezrules.models.backend_core import Case, CaseEvent, IntegrationEvent, IntegrationSubscription, User

router = APIRouter(prefix="/api/v2", tags=["Cases"])


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


def _case_to_response(case: Case) -> CaseResponse:
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
        assigned_to_user_id=int(case.assigned_to_user_id) if case.assigned_to_user_id is not None else None,
        resolved_by_user_id=int(case.resolved_by_user_id) if case.resolved_by_user_id is not None else None,
        resolution_note=str(case.resolution_note) if case.resolution_note else None,
        resolution_label_id=int(case.resolution_label_id) if case.resolution_label_id is not None else None,
        reopened_from_case_id=int(case.reopened_from_case_id) if case.reopened_from_case_id is not None else None,
        created_at=case.created_at,  # type: ignore[arg-type]
        updated_at=case.updated_at,  # type: ignore[arg-type]
        resolved_at=case.resolved_at if case.resolved_at else None,  # type: ignore[arg-type]
    )


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
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.VIEW_CASES)),
    current_org_id: int = Depends(get_current_org_id),
    db: Any = Depends(get_db),
) -> CaseListResponse:
    query = db.query(Case).filter(Case.o_id == current_org_id)
    if status_filter:
        query = query.filter(Case.status == status_filter)
    if outcome:
        query = query.filter(Case.resolved_outcome == outcome.strip().upper())
    total = int(query.count())
    cases = query.order_by(Case.updated_at.desc(), Case.case_id.desc()).offset(offset).limit(limit).all()
    return CaseListResponse(cases=[_case_to_response(case) for case in cases], total=total)


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
    return CaseDetailResponse(case=_case_to_response(case), events=[_case_event_to_response(event) for event in events])


@router.patch("/cases/{case_id}", response_model=CaseMutationResponse)
def update_case(
    case_id: int,
    payload: CaseUpdateRequest,
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.MANAGE_CASES)),
    current_org_id: int = Depends(get_current_org_id),
    db: Any = Depends(get_db),
) -> CaseMutationResponse:
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
    return CaseMutationResponse(success=True, message="Case updated", case=_case_to_response(case))


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
            resolution_note=payload.resolution_note,
            resolution_label_id=payload.resolution_label_id,
            expected_current_ed_id=payload.expected_current_ed_id,
        )
    except CaseNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found") from exc
    except CaseConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    db.commit()
    return CaseMutationResponse(success=True, message="Case resolved", case=_case_to_response(case))


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
    config = dict(payload.config) if payload.config is not None else dict(subscription.config or {})
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
