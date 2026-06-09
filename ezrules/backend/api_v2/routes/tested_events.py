"""
FastAPI routes for viewing recently tested events and triggered rules.
"""

from collections import defaultdict
from datetime import UTC, datetime
from typing import Any, cast

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import tuple_

from ezrules.backend.api_v2.auth.dependencies import (
    get_current_active_user,
    get_current_org_id,
    get_db,
    require_permission,
)
from ezrules.backend.api_v2.schemas.tested_events import (
    TestedEventGraphEdge,
    TestedEventGraphNode,
    TestedEventGraphResponse,
    TestedEventItem,
    TestedEventsResponse,
    TriggeredRuleItem,
)
from ezrules.core.permissions_constants import PermissionAction
from ezrules.core.rule import Rule as ParsedRule
from ezrules.models.backend_core import (
    EvaluationDecision,
    EvaluationRuleResult,
    EventVersion,
    EventVersionLabel,
    GraphEventEntityLink,
    Label,
    Rule,
    TransactionCurrentVersion,
    User,
)

router = APIRouter(prefix="/api/v2/tested-events", tags=["Tested Events"])


def _utc_isoformat(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _extract_referenced_fields(rule_logic: str) -> list[str]:
    """Extract top-level event fields referenced by a rule."""
    try:
        parsed_rule = ParsedRule(rid="", logic=rule_logic)
        return sorted(str(param) for param in parsed_rule.get_rule_params())
    except Exception:
        return []


def _event_node_id(ev_id: int) -> str:
    return f"event:{ev_id}"


def _entity_node_id(entity_type: str, entity_value_hash: str) -> str:
    return f"entity:{entity_type}:{entity_value_hash}"


def _event_node(event_version: EventVersion, *, root: bool = False) -> TestedEventGraphNode:
    return TestedEventGraphNode(
        id=_event_node_id(int(event_version.ev_id)),
        kind="event",
        label=str(event_version.transaction_id),
        transaction_id=str(event_version.transaction_id),
        event_version=int(event_version.event_version),
        effective_at=_utc_isoformat(cast(datetime, event_version.effective_at)),
        root=root,
    )


def _entity_node(link: GraphEventEntityLink) -> TestedEventGraphNode:
    entity_type = str(link.entity_type)
    entity_value_hash = str(link.entity_value_hash)
    entity_value = str(link.entity_value) if link.entity_value is not None else entity_value_hash[:12]
    return TestedEventGraphNode(
        id=_entity_node_id(entity_type, entity_value_hash),
        kind="entity",
        label=f"{entity_type}: {entity_value}",
        entity_type=entity_type,
        entity_value=entity_value,
        entity_value_hash=entity_value_hash,
        expandable=True,
    )


def _graph_edge(link: GraphEventEntityLink) -> TestedEventGraphEdge:
    source = _event_node_id(int(link.ev_id))
    target = _entity_node_id(str(link.entity_type), str(link.entity_value_hash))
    field_path = str(link.field_path)
    return TestedEventGraphEdge(
        id=f"{source}->{target}:{field_path}",
        source=source,
        target=target,
        label=field_path,
        field_path=field_path,
    )


def _load_event_links(
    db: Any,
    current_org_id: int,
    ev_ids: list[int],
    links_by_ev_id: dict[int, list[GraphEventEntityLink]],
) -> None:
    missing_ev_ids = sorted({ev_id for ev_id in ev_ids if ev_id not in links_by_ev_id})
    if not missing_ev_ids:
        return

    for ev_id in missing_ev_ids:
        links_by_ev_id[ev_id] = []

    link_rows = (
        db.query(GraphEventEntityLink)
        .filter(GraphEventEntityLink.o_id == current_org_id, GraphEventEntityLink.ev_id.in_(missing_ev_ids))
        .order_by(
            GraphEventEntityLink.ev_id.asc(),
            GraphEventEntityLink.entity_type.asc(),
            GraphEventEntityLink.field_path.asc(),
        )
        .all()
    )
    for link in link_rows:
        links_by_ev_id[int(link.ev_id)].append(link)


def _event_links(
    db: Any,
    current_org_id: int,
    event_version: EventVersion,
    links_by_ev_id: dict[int, list[GraphEventEntityLink]],
) -> list[GraphEventEntityLink]:
    ev_id = int(event_version.ev_id)
    _load_event_links(db, current_org_id, [ev_id], links_by_ev_id)
    return links_by_ev_id[ev_id]


def _add_event_links(
    db: Any,
    current_org_id: int,
    event_version: EventVersion,
    *,
    nodes: dict[str, TestedEventGraphNode],
    edges: dict[str, TestedEventGraphEdge],
    links_by_ev_id: dict[int, list[GraphEventEntityLink]],
    root: bool = False,
) -> list[GraphEventEntityLink]:
    event_node = _event_node(event_version, root=root)
    nodes[event_node.id] = event_node
    links = _event_links(db, current_org_id, event_version, links_by_ev_id)
    for link in links:
        entity_node = _entity_node(link)
        nodes[entity_node.id] = entity_node
        edge = _graph_edge(link)
        edges[edge.id] = edge
    return links


def _linked_event_versions_for_entities(
    db: Any,
    current_org_id: int,
    *,
    entity_keys: set[tuple[str, str]],
    max_events: int,
) -> tuple[list[EventVersion], bool]:
    if not entity_keys:
        return [], False

    link_rows = (
        db.query(GraphEventEntityLink.ev_id)
        .filter(
            GraphEventEntityLink.o_id == current_org_id,
            tuple_(GraphEventEntityLink.entity_type, GraphEventEntityLink.entity_value_hash).in_(sorted(entity_keys)),
        )
        .order_by(GraphEventEntityLink.effective_at.desc(), GraphEventEntityLink.ev_id.desc())
        .limit((max_events * len(entity_keys)) + 1)
        .all()
    )
    ev_ids: list[int] = []
    for row in link_rows:
        ev_id = int(row.ev_id)
        if ev_id not in ev_ids:
            ev_ids.append(ev_id)
        if len(ev_ids) > max_events:
            break

    truncated = len(ev_ids) > max_events
    ev_ids = ev_ids[:max_events]
    if not ev_ids:
        return [], False

    event_versions = (
        db.query(EventVersion)
        .filter(EventVersion.o_id == current_org_id, EventVersion.ev_id.in_(ev_ids))
        .order_by(EventVersion.effective_at.desc(), EventVersion.ev_id.desc())
        .all()
    )
    event_versions_by_id = {int(event_version.ev_id): event_version for event_version in event_versions}
    return [event_versions_by_id[ev_id] for ev_id in ev_ids if ev_id in event_versions_by_id], truncated


def _linked_event_versions_for_links(
    db: Any,
    current_org_id: int,
    links: list[GraphEventEntityLink],
    *,
    root_event_version: EventVersion,
    root_ev_id: int,
    max_events: int,
    max_hops: int,
    links_by_ev_id: dict[int, list[GraphEventEntityLink]],
) -> tuple[list[EventVersion], bool]:
    discovered: list[EventVersion] = []
    visited_ev_ids = {root_ev_id}
    frontier: list[tuple[EventVersion, list[GraphEventEntityLink], int]] = [(root_event_version, links, 0)]
    truncated = False

    while frontier and len(discovered) < max_events:
        _event_version, event_links, depth = frontier.pop(0)
        if depth >= max_hops:
            continue

        seen_entities: set[tuple[str, str]] = set()
        for link in event_links:
            entity_key = (str(link.entity_type), str(link.entity_value_hash))
            if entity_key in seen_entities:
                continue
            seen_entities.add(entity_key)

        linked_event_versions, entity_truncated = _linked_event_versions_for_entities(
            db,
            current_org_id,
            entity_keys=seen_entities,
            max_events=max_events,
        )
        truncated = truncated or entity_truncated
        linked_event_versions = [
            linked_event_version
            for linked_event_version in linked_event_versions
            if int(linked_event_version.ev_id) not in visited_ev_ids
        ]
        if depth + 1 < max_hops:
            _load_event_links(
                db,
                current_org_id,
                [int(linked_event_version.ev_id) for linked_event_version in linked_event_versions],
                links_by_ev_id,
            )
        for linked_event_version in linked_event_versions:
            linked_ev_id = int(linked_event_version.ev_id)
            if len(discovered) >= max_events:
                truncated = True
                break
            visited_ev_ids.add(linked_ev_id)
            discovered.append(linked_event_version)
            if depth + 1 < max_hops:
                frontier.append((linked_event_version, links_by_ev_id[linked_ev_id], depth + 1))
            if len(discovered) >= max_events:
                break

    return discovered, truncated


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
        db.query(EvaluationDecision, EventVersion, TransactionCurrentVersion, Label.label)
        .join(EventVersion, EventVersion.ev_id == EvaluationDecision.ev_id)
        .join(
            TransactionCurrentVersion,
            (TransactionCurrentVersion.o_id == EvaluationDecision.o_id)
            & (TransactionCurrentVersion.transaction_id == EvaluationDecision.transaction_id),
        )
        .outerjoin(
            EventVersionLabel,
            (EventVersionLabel.ev_id == EvaluationDecision.ev_id) & (EventVersionLabel.o_id == EvaluationDecision.o_id),
        )
        .outerjoin(Label, (Label.el_id == EventVersionLabel.el_id) & (Label.o_id == EvaluationDecision.o_id))
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
    decision_ids = [int(decision.ed_id) for decision, _event_version, _current_version, _label_name in records]

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
            evaluation_decision_id=int(decision.ed_id),
            transaction_id=str(decision.transaction_id),
            effective_at=_utc_isoformat(decision.effective_at),
            observed_at=_utc_isoformat(decision.observed_at),
            first_effective_at=_utc_isoformat(current_version.first_effective_at),
            first_observed_at=_utc_isoformat(current_version.first_observed_at),
            event_version=int(decision.event_version),
            is_current=bool(decision.is_current),
            resolved_outcome=str(decision.resolved_outcome) if decision.resolved_outcome is not None else None,
            label_name=str(label_name) if label_name is not None else None,
            outcome_counters=dict(decision.outcome_counters or {}),
            event_data=dict(event_version.event_data or {}),
            triggered_rules=triggered_rules_by_decision.get(int(decision.ed_id), []),
        )
        for decision, event_version, current_version, label_name in records
    ]

    return TestedEventsResponse(events=events, total=int(total), limit=limit)


@router.get("/{evaluation_decision_id}/graph", response_model=TestedEventGraphResponse)
def tested_event_graph(
    evaluation_decision_id: int,
    max_events: int = Query(default=25, ge=1, le=100, description="Maximum linked event nodes to include"),
    max_hops: int = Query(default=3, ge=1, le=5, description="Maximum event-to-event graph hops to traverse"),
    expand_entity_type: str | None = Query(default=None, description="Entity type to expand from"),
    expand_entity_value_hash: str | None = Query(default=None, description="Entity value hash to expand from"),
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.VIEW_RULES)),
    current_org_id: int = Depends(get_current_org_id),
    db: Any = Depends(get_db),
) -> TestedEventGraphResponse:
    """Return a bounded graph around a tested event, optionally expanded from one entity node."""
    decision = (
        db.query(EvaluationDecision)
        .filter(EvaluationDecision.o_id == current_org_id, EvaluationDecision.ed_id == evaluation_decision_id)
        .first()
    )
    if decision is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tested event not found")

    root_event_version = (
        db.query(EventVersion)
        .filter(EventVersion.o_id == current_org_id, EventVersion.ev_id == int(decision.ev_id))
        .first()
    )
    if root_event_version is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event version not found")

    nodes: dict[str, TestedEventGraphNode] = {}
    edges: dict[str, TestedEventGraphEdge] = {}
    links_by_ev_id: dict[int, list[GraphEventEntityLink]] = {}
    root_event_node_id = _event_node_id(int(root_event_version.ev_id))
    root_links = _add_event_links(
        db,
        current_org_id,
        root_event_version,
        nodes=nodes,
        edges=edges,
        links_by_ev_id=links_by_ev_id,
        root=True,
    )
    linked_event_limit = max(0, max_events - 1)

    truncated = False
    if linked_event_limit == 0:
        truncated = bool(root_links)
    elif expand_entity_type and expand_entity_value_hash:
        event_versions, truncated = _linked_event_versions_for_entities(
            db,
            current_org_id,
            entity_keys={(expand_entity_type, expand_entity_value_hash)},
            max_events=linked_event_limit,
        )
        _load_event_links(
            db, current_org_id, [int(event_version.ev_id) for event_version in event_versions], links_by_ev_id
        )
        for event_version in event_versions:
            if int(event_version.ev_id) != int(root_event_version.ev_id):
                _add_event_links(
                    db,
                    current_org_id,
                    event_version,
                    nodes=nodes,
                    edges=edges,
                    links_by_ev_id=links_by_ev_id,
                    root=False,
                )
    else:
        event_versions, truncated = _linked_event_versions_for_links(
            db,
            current_org_id,
            root_links,
            root_event_version=root_event_version,
            root_ev_id=int(root_event_version.ev_id),
            max_events=linked_event_limit,
            max_hops=max_hops,
            links_by_ev_id=links_by_ev_id,
        )
        _load_event_links(
            db, current_org_id, [int(event_version.ev_id) for event_version in event_versions], links_by_ev_id
        )
        for event_version in event_versions:
            _add_event_links(
                db,
                current_org_id,
                event_version,
                nodes=nodes,
                edges=edges,
                links_by_ev_id=links_by_ev_id,
                root=False,
            )

    event_count = sum(1 for node in nodes.values() if node.kind == "event")
    return TestedEventGraphResponse(
        nodes=list(nodes.values()),
        edges=list(edges.values()),
        root_event_node_id=root_event_node_id,
        max_events=max_events,
        max_hops=max_hops,
        event_count=event_count,
        truncated=truncated,
    )
