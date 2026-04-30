from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ezrules.backend.api_v2.auth.dependencies import (
    get_current_active_user,
    get_current_org_id,
    get_db,
    require_permission,
)
from ezrules.backend.api_v2.schemas.alerts import (
    AlertIncidentResponse,
    AlertIncidentsResponse,
    AlertMutationResponse,
    AlertRuleCreate,
    AlertRuleResponse,
    AlertRulesResponse,
    AlertRuleUpdate,
    NotificationResponse,
    NotificationsResponse,
    NotificationUnreadCountResponse,
)
from ezrules.backend.notifications.dispatcher import ensure_default_policy
from ezrules.core.audit_helpers import save_alert_rule_history
from ezrules.core.permissions_constants import PermissionAction
from ezrules.models.backend_core import (
    AlertIncident,
    AlertRule,
    AllowedOutcome,
    InAppNotification,
    InAppNotificationRead,
    User,
)

router = APIRouter(prefix="/api/v2", tags=["Alerts"])


def _alert_rule_to_response(rule: AlertRule) -> AlertRuleResponse:
    return AlertRuleResponse(
        id=int(rule.ar_id),
        name=str(rule.name),
        outcome=str(rule.outcome),
        threshold=int(rule.threshold),
        window_seconds=int(rule.window_seconds),
        cooldown_seconds=int(rule.cooldown_seconds),
        enabled=bool(rule.enabled),
        created_at=rule.created_at,  # type: ignore[arg-type]
        updated_at=rule.updated_at,  # type: ignore[arg-type]
    )


def _alert_incident_to_response(incident: AlertIncident) -> AlertIncidentResponse:
    return AlertIncidentResponse(
        id=int(incident.ai_id),
        alert_rule_id=int(incident.alert_rule_id),
        outcome=str(incident.outcome),
        observed_count=int(incident.observed_count),
        threshold=int(incident.threshold),
        window_start=incident.window_start,  # type: ignore[arg-type]
        window_end=incident.window_end,  # type: ignore[arg-type]
        status=incident.status,  # type: ignore[arg-type]
        triggered_at=incident.triggered_at,  # type: ignore[arg-type]
        acknowledged_at=incident.acknowledged_at if incident.acknowledged_at else None,  # type: ignore[arg-type]
        acknowledged_by=str(incident.acknowledged_by) if incident.acknowledged_by else None,
    )


def _notification_to_response(notification: InAppNotification, read_at: datetime | None) -> NotificationResponse:
    return NotificationResponse(
        id=int(notification.ian_id),
        severity=str(notification.severity),
        title=str(notification.title),
        body=str(notification.body),
        action_url=str(notification.action_url) if notification.action_url else None,
        source_type=str(notification.source_type),
        source_id=int(notification.source_id),
        created_at=notification.created_at,  # type: ignore[arg-type]
        read_at=read_at,
    )


def _validate_alert_outcome(db: Any, current_org_id: int, outcome: str) -> str:
    normalized_outcome = outcome.strip().upper()
    exists = (
        db.query(AllowedOutcome)
        .filter(AllowedOutcome.o_id == current_org_id, AllowedOutcome.outcome_name == normalized_outcome)
        .first()
    )
    if exists is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Outcome '{normalized_outcome}' is not configured for this organization",
        )
    return normalized_outcome


@router.get("/alerts/rules", response_model=AlertRulesResponse)
def list_alert_rules(
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.VIEW_ALERTS)),
    current_org_id: int = Depends(get_current_org_id),
    db: Any = Depends(get_db),
) -> AlertRulesResponse:
    rules = (
        db.query(AlertRule)
        .filter(AlertRule.o_id == current_org_id)
        .order_by(AlertRule.created_at.desc(), AlertRule.ar_id.desc())
        .all()
    )
    return AlertRulesResponse(rules=[_alert_rule_to_response(rule) for rule in rules])


@router.post("/alerts/rules", response_model=AlertMutationResponse, status_code=status.HTTP_201_CREATED)
def create_alert_rule(
    payload: AlertRuleCreate,
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.MANAGE_ALERTS)),
    current_org_id: int = Depends(get_current_org_id),
    db: Any = Depends(get_db),
) -> AlertMutationResponse:
    outcome = _validate_alert_outcome(db, current_org_id, payload.outcome)
    rule = AlertRule(
        o_id=current_org_id,
        name=payload.name.strip(),
        outcome=outcome,
        threshold=payload.threshold,
        window_seconds=payload.window_seconds,
        cooldown_seconds=payload.cooldown_seconds,
        enabled=payload.enabled,
    )
    db.add(rule)
    db.flush()
    ensure_default_policy(db, o_id=current_org_id, alert_rule_id=int(rule.ar_id))
    save_alert_rule_history(
        db,
        alert_rule_id=int(rule.ar_id),
        name=str(rule.name),
        action="created",
        o_id=current_org_id,
        changed_by=str(user.email) if user.email else None,
        details=f"outcome={rule.outcome}, threshold={rule.threshold}, window_seconds={rule.window_seconds}",
    )
    db.commit()
    return AlertMutationResponse(success=True, message="Alert rule created", rule=_alert_rule_to_response(rule))


@router.patch("/alerts/rules/{rule_id}", response_model=AlertMutationResponse)
def update_alert_rule(
    rule_id: int,
    payload: AlertRuleUpdate,
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.MANAGE_ALERTS)),
    current_org_id: int = Depends(get_current_org_id),
    db: Any = Depends(get_db),
) -> AlertMutationResponse:
    rule = db.query(AlertRule).filter(AlertRule.o_id == current_org_id, AlertRule.ar_id == rule_id).first()
    if rule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert rule not found")

    if payload.name is not None:
        rule.name = payload.name.strip()
    if payload.outcome is not None:
        rule.outcome = _validate_alert_outcome(db, current_org_id, payload.outcome)
    if payload.threshold is not None:
        rule.threshold = payload.threshold
    if payload.window_seconds is not None:
        rule.window_seconds = payload.window_seconds
    if payload.cooldown_seconds is not None:
        rule.cooldown_seconds = payload.cooldown_seconds
    if payload.enabled is not None:
        rule.enabled = payload.enabled
    rule.updated_at = datetime.now(UTC)

    save_alert_rule_history(
        db,
        alert_rule_id=int(rule.ar_id),
        name=str(rule.name),
        action="updated",
        o_id=current_org_id,
        changed_by=str(user.email) if user.email else None,
        details=f"outcome={rule.outcome}, threshold={rule.threshold}, window_seconds={rule.window_seconds}",
    )
    db.commit()
    return AlertMutationResponse(success=True, message="Alert rule updated", rule=_alert_rule_to_response(rule))


@router.get("/alerts/incidents", response_model=AlertIncidentsResponse)
def list_alert_incidents(
    limit: int = Query(default=50, ge=1, le=200),
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.VIEW_ALERTS)),
    current_org_id: int = Depends(get_current_org_id),
    db: Any = Depends(get_db),
) -> AlertIncidentsResponse:
    incidents = (
        db.query(AlertIncident)
        .filter(AlertIncident.o_id == current_org_id)
        .order_by(AlertIncident.triggered_at.desc(), AlertIncident.ai_id.desc())
        .limit(limit)
        .all()
    )
    return AlertIncidentsResponse(incidents=[_alert_incident_to_response(incident) for incident in incidents])


@router.post("/alerts/incidents/{incident_id}/acknowledge", response_model=AlertMutationResponse)
def acknowledge_alert_incident(
    incident_id: int,
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.VIEW_ALERTS)),
    current_org_id: int = Depends(get_current_org_id),
    db: Any = Depends(get_db),
) -> AlertMutationResponse:
    incident = (
        db.query(AlertIncident).filter(AlertIncident.o_id == current_org_id, AlertIncident.ai_id == incident_id).first()
    )
    if incident is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert incident not found")
    incident.status = "acknowledged"
    incident.acknowledged_at = datetime.now(UTC)
    incident.acknowledged_by = str(user.email) if user.email else None
    db.commit()
    return AlertMutationResponse(
        success=True,
        message="Alert incident acknowledged",
        incident=_alert_incident_to_response(incident),
    )


def _notification_query(db: Any, current_org_id: int, user_id: int, unread_only: bool) -> Any:
    query = (
        db.query(InAppNotification, InAppNotificationRead.read_at)
        .outerjoin(
            InAppNotificationRead,
            (InAppNotificationRead.notification_id == InAppNotification.ian_id)
            & (InAppNotificationRead.user_id == user_id),
        )
        .filter(InAppNotification.o_id == current_org_id)
    )
    if unread_only:
        query = query.filter(InAppNotificationRead.ianr_id.is_(None))
    return query


@router.get("/notifications", response_model=NotificationsResponse)
def list_notifications(
    unread_only: bool = Query(default=False),
    limit: int = Query(default=10, ge=1, le=100),
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.VIEW_ALERTS)),
    current_org_id: int = Depends(get_current_org_id),
    db: Any = Depends(get_db),
) -> NotificationsResponse:
    rows = (
        _notification_query(db, current_org_id, int(user.id), unread_only)
        .order_by(InAppNotification.created_at.desc(), InAppNotification.ian_id.desc())
        .limit(limit)
        .all()
    )
    return NotificationsResponse(
        notifications=[_notification_to_response(notification, read_at) for notification, read_at in rows]
    )


@router.get("/notifications/unread-count", response_model=NotificationUnreadCountResponse)
def get_unread_notification_count(
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.VIEW_ALERTS)),
    current_org_id: int = Depends(get_current_org_id),
    db: Any = Depends(get_db),
) -> NotificationUnreadCountResponse:
    count = _notification_query(db, current_org_id, int(user.id), True).count()
    return NotificationUnreadCountResponse(unread_count=int(count))


@router.post("/notifications/{notification_id}/read", response_model=NotificationUnreadCountResponse)
def mark_notification_read(
    notification_id: int,
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.VIEW_ALERTS)),
    current_org_id: int = Depends(get_current_org_id),
    db: Any = Depends(get_db),
) -> NotificationUnreadCountResponse:
    notification = (
        db.query(InAppNotification)
        .filter(InAppNotification.o_id == current_org_id, InAppNotification.ian_id == notification_id)
        .first()
    )
    if notification is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
    existing = (
        db.query(InAppNotificationRead)
        .filter(InAppNotificationRead.notification_id == notification_id, InAppNotificationRead.user_id == user.id)
        .first()
    )
    if existing is None:
        db.add(InAppNotificationRead(notification_id=notification_id, user_id=int(user.id)))
        db.commit()
    return get_unread_notification_count(user=user, current_org_id=current_org_id, db=db)


@router.post("/notifications/read-all", response_model=NotificationUnreadCountResponse)
def mark_all_notifications_read(
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.VIEW_ALERTS)),
    current_org_id: int = Depends(get_current_org_id),
    db: Any = Depends(get_db),
) -> NotificationUnreadCountResponse:
    rows = _notification_query(db, current_org_id, int(user.id), True).all()
    for notification, _read_at in rows:
        db.add(InAppNotificationRead(notification_id=int(notification.ian_id), user_id=int(user.id)))
    db.commit()
    return NotificationUnreadCountResponse(unread_count=0)
