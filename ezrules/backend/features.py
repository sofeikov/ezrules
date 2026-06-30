from __future__ import annotations

import hashlib
import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy import false, func, or_, text, tuple_

from ezrules.backend.api_v2.schemas.features import ALLOWED_WINDOW_SECONDS, FeatureAggregation
from ezrules.core.field_paths import get_field_value, split_field_path
from ezrules.core.rule_helpers import StatReferenceExtractor
from ezrules.models.backend_core import (
    EventVersion,
    FeatureDefinition,
    FeatureSnapshotResolution,
    GraphEntityField,
    GraphEventEntityLink,
)
from ezrules.models.backend_core import Rule as RuleModel

MAX_STAT_REFERENCES_PER_RULE = 10
MAX_ACTIVE_FEATURES_PER_ORG = 100
FEATURE_STATEMENT_TIMEOUT_MS = 750
DEFAULT_GRAPH_MAX_DEPTH = 4
DEFAULT_GRAPH_MAX_EXPANDED_NODES = 10_000
HARD_GRAPH_MAX_DEPTH = 6
HARD_GRAPH_MAX_EXPANDED_NODES = 50_000


class FeatureResolutionError(Exception):
    """Raised when a referenced stat cannot be resolved for rule evaluation."""


@dataclass(frozen=True)
class FeatureComputationResult:
    value: Any
    matched_event_count: int
    as_of: datetime
    window_start: datetime
    entity_value_hash: str | None = None


@dataclass(frozen=True)
class FeatureResolutionTrace:
    stat_path: str
    feature_id: int | None
    feature_kind: str | None
    feature_version: int | None
    as_of: datetime
    window_start: datetime
    matched_event_count: int
    entity_value_hash: str | None
    resolution_status: str
    warning: str | None = None


def normalize_as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def feature_path(feature: FeatureDefinition) -> str:
    return f"{feature.entity}.{feature.feature_name}"


def extract_rule_stat_paths(rule_source: str) -> list[str]:
    return list(dict.fromkeys(StatReferenceExtractor().extract(rule_source)))


def get_feature_dependencies(db: Any, o_id: int, stat_path: str) -> list[RuleModel]:
    token = f"stat[{stat_path}]"
    candidates = (
        db.query(RuleModel)
        .filter(RuleModel.o_id == o_id, RuleModel.logic.contains(token))
        .order_by(RuleModel.r_id.asc())
        .all()
    )
    return [rule for rule in candidates if stat_path in extract_rule_stat_paths(str(rule.logic))]


def validate_feature_reference_budget(stat_paths: set[str]) -> None:
    if len(stat_paths) > MAX_STAT_REFERENCES_PER_RULE:
        raise FeatureResolutionError(
            f"Rules may reference at most {MAX_STAT_REFERENCES_PER_RULE} computed stats; found {len(stat_paths)}"
        )


def _safe_get(event_data: dict[str, Any], path: str) -> Any:
    try:
        return get_field_value(event_data, path)
    except KeyError:
        return None


def _filter_matches(event_data: dict[str, Any], filters: list[dict[str, Any]]) -> bool:
    for filter_config in filters:
        value = _safe_get(event_data, str(filter_config.get("field")))
        operator = filter_config.get("operator", "eq")
        expected = filter_config.get("value")
        if operator == "eq" and value != expected:
            return False
        if operator == "in" and value not in (expected if isinstance(expected, list) else []):
            return False
    return True


def _jsonb_text_value(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _graph_entity_value_hash(entity_value: str) -> str:
    return hashlib.sha256(entity_value.encode("utf-8")).hexdigest()


def _entity_value_hash(entity_value: Any) -> str | None:
    text_value = _jsonb_text_value(entity_value)
    if not text_value:
        return None
    return _graph_entity_value_hash(text_value)


def _graph_entity_values(event_data: dict[str, Any], field_path: str) -> list[str]:
    value = _safe_get(event_data, field_path)
    if value is None:
        return []
    raw_values = value if isinstance(value, list) else [value]
    normalized: list[str] = []
    for raw_value in raw_values:
        if isinstance(raw_value, dict | list):
            continue
        text_value = _jsonb_text_value(raw_value)
        if text_value is not None and text_value:
            normalized.append(text_value)
    return list(dict.fromkeys(normalized))


def persist_graph_links_for_event(db: Any, o_id: int, event_version: EventVersion) -> int:
    fields = (
        db.query(GraphEntityField)
        .filter(GraphEntityField.o_id == o_id, GraphEntityField.status == "active")
        .order_by(GraphEntityField.field_path.asc())
        .all()
    )
    if not fields:
        return 0

    db.query(GraphEventEntityLink).filter(
        GraphEventEntityLink.o_id == o_id,
        GraphEventEntityLink.ev_id == int(event_version.ev_id),
    ).delete(synchronize_session=False)

    inserted = 0
    event_data = cast(dict[str, Any], event_version.event_data)
    for field in fields:
        for entity_value in _graph_entity_values(event_data, str(field.field_path)):
            db.add(
                GraphEventEntityLink(
                    o_id=o_id,
                    ev_id=int(event_version.ev_id),
                    transaction_id=str(event_version.transaction_id),
                    effective_at=cast(datetime, event_version.effective_at),
                    field_path=str(field.field_path),
                    entity_type=str(field.entity_type),
                    entity_value=entity_value[:1024],
                    entity_value_hash=_graph_entity_value_hash(entity_value),
                )
            )
            inserted += 1
    return inserted


def _event_data_text_expression(path: str) -> Any:
    return func.jsonb_extract_path_text(EventVersion.event_data, *split_field_path(path))


def _apply_jsonb_filter(query: Any, filter_config: dict[str, Any]) -> Any:
    field = str(filter_config.get("field") or "")
    if not field:
        return query

    expression = _event_data_text_expression(field)
    operator = filter_config.get("operator", "eq")
    expected = filter_config.get("value")

    if operator == "eq":
        expected_value = _jsonb_text_value(expected)
        return query.filter(expression.is_(None) if expected_value is None else expression == expected_value)

    if operator == "in":
        expected_values = expected if isinstance(expected, list) else []
        if not expected_values:
            return query.filter(false())
        text_values = [_jsonb_text_value(item) for item in expected_values]
        non_null_values = [item for item in text_values if item is not None]
        predicates = []
        if non_null_values:
            predicates.append(expression.in_(non_null_values))
        if None in text_values:
            predicates.append(expression.is_(None))
        return query.filter(or_(*predicates) if predicates else false())

    return query


def _coerce_number(value: Any, *, null_handling: str) -> float | None:
    if value is None:
        return 0.0 if null_handling == "zero" else None
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, int | float):
        if math.isnan(value) or math.isinf(value):
            return None
        return float(value)
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


def _compute_aggregate(
    feature: FeatureDefinition,
    matched_events: list[EventVersion],
    *,
    as_of: datetime,
) -> Any:
    aggregation = str(feature.aggregation_type)
    if aggregation == FeatureAggregation.COUNT.value:
        return len(matched_events)

    values = [_safe_get(cast(dict[str, Any], event.event_data), str(feature.source_field)) for event in matched_events]

    if aggregation == FeatureAggregation.COUNT_DISTINCT.value:
        return len({value for value in values if value is not None})

    if aggregation == FeatureAggregation.DAYS_SINCE_FIRST_SEEN.value:
        if not matched_events:
            return None
        first_seen = min(normalize_as_utc(cast(datetime, event.effective_at)) for event in matched_events)
        return max(0, (as_of - first_seen).days)

    numeric_values = [_coerce_number(value, null_handling=str(feature.null_handling)) for value in values]
    numeric_values = [value for value in numeric_values if value is not None]

    if not numeric_values:
        return None
    if aggregation == FeatureAggregation.SUM.value:
        return sum(numeric_values)
    if aggregation == FeatureAggregation.AVG.value:
        return sum(numeric_values) / len(numeric_values)
    if aggregation == FeatureAggregation.MIN.value:
        return min(numeric_values)
    if aggregation == FeatureAggregation.MAX.value:
        return max(numeric_values)
    if aggregation == FeatureAggregation.STDDEV.value:
        mean = sum(numeric_values) / len(numeric_values)
        return math.sqrt(sum((value - mean) ** 2 for value in numeric_values) / len(numeric_values))
    raise FeatureResolutionError(f"Unsupported feature aggregation '{aggregation}'")


def _compute_aggregate_feature(
    db: Any,
    o_id: int,
    feature: FeatureDefinition,
    event_data: dict[str, Any],
    as_of: datetime,
) -> FeatureComputationResult:
    as_of = normalize_as_utc(as_of)
    entity_value = _safe_get(event_data, str(feature.entity_key))
    if entity_value is None:
        return FeatureComputationResult(value=None, matched_event_count=0, as_of=as_of, window_start=as_of)

    if int(feature.window_seconds) not in ALLOWED_WINDOW_SECONDS:
        raise FeatureResolutionError("Feature window is not an allowed online preset")

    window_start = as_of - timedelta(seconds=int(feature.window_seconds))
    try:
        db.execute(
            text("SELECT set_config('statement_timeout', :timeout_ms, true)"),
            {"timeout_ms": str(FEATURE_STATEMENT_TIMEOUT_MS)},
        )
    except Exception as exc:
        raise FeatureResolutionError("Unable to apply feature query timeout") from exc

    entity_text_value = _jsonb_text_value(entity_value)
    query = db.query(EventVersion).filter(
        EventVersion.o_id == o_id,
        EventVersion.effective_at >= window_start,
        EventVersion.effective_at < as_of,
        EventVersion.observed_at <= as_of,
        _event_data_text_expression(str(feature.entity_key)) == entity_text_value,
    )
    filters = list(cast(list[dict[str, Any]], feature.filters or []))
    for filter_config in filters:
        query = _apply_jsonb_filter(query, filter_config)
    candidate_events = query.order_by(EventVersion.effective_at.asc(), EventVersion.ev_id.asc()).all()
    current_event_ids = _current_event_version_ids_as_of(
        db,
        o_id,
        {str(event.transaction_id) for event in candidate_events},
        as_of,
    )
    matched_events = [event for event in candidate_events if int(event.ev_id) in current_event_ids]
    return FeatureComputationResult(
        value=_compute_aggregate(feature, matched_events, as_of=as_of),
        matched_event_count=len(matched_events),
        as_of=as_of,
        window_start=window_start,
        entity_value_hash=_entity_value_hash(entity_value),
    )


def _graph_config_value(feature: FeatureDefinition, key: str, default: Any = None) -> Any:
    config = feature.graph_config if isinstance(feature.graph_config, dict) else {}
    return config.get(key, default)


def _bounded_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(parsed, maximum))


def _current_event_version_ids_as_of(db: Any, o_id: int, transaction_ids: set[str], as_of: datetime) -> set[int]:
    if not transaction_ids:
        return set()

    ranked_versions = (
        db.query(
            EventVersion.ev_id.label("ev_id"),
            func.row_number()
            .over(
                partition_by=EventVersion.transaction_id,
                order_by=(
                    EventVersion.terminal_state.desc(),
                    EventVersion.effective_at.desc(),
                    EventVersion.observed_at.desc(),
                    EventVersion.ev_id.desc(),
                ),
            )
            .label("row_number"),
        )
        .filter(
            EventVersion.o_id == o_id,
            EventVersion.transaction_id.in_(sorted(transaction_ids)),
            EventVersion.observed_at <= as_of,
        )
        .subquery()
    )
    rows = db.query(ranked_versions.c.ev_id).filter(ranked_versions.c.row_number == 1).all()
    return {int(row.ev_id) for row in rows}


def _compute_graph_distinct_count(
    db: Any,
    o_id: int,
    feature: FeatureDefinition,
    event_data: dict[str, Any],
    as_of: datetime,
) -> FeatureComputationResult:
    as_of = normalize_as_utc(as_of)
    entity_value = _safe_get(event_data, str(feature.entity_key))
    if entity_value is None:
        return FeatureComputationResult(value=None, matched_event_count=0, as_of=as_of, window_start=as_of)

    if int(feature.window_seconds) not in ALLOWED_WINDOW_SECONDS:
        raise FeatureResolutionError("Feature window is not an allowed online preset")

    target_entity = str(_graph_config_value(feature, "target_entity", "")).strip()
    allowed_entity_types = [
        str(item).strip()
        for item in cast(list[Any], _graph_config_value(feature, "allowed_entity_types", []))
        if str(item).strip()
    ]
    if not target_entity or not allowed_entity_types:
        raise FeatureResolutionError("Graph feature requires target_entity and allowed_entity_types")
    if str(feature.entity) not in allowed_entity_types or target_entity not in allowed_entity_types:
        raise FeatureResolutionError("Graph feature start and target entities must be traversable")

    max_depth = _bounded_int(
        _graph_config_value(feature, "max_depth"),
        default=DEFAULT_GRAPH_MAX_DEPTH,
        minimum=1,
        maximum=HARD_GRAPH_MAX_DEPTH,
    )
    max_expanded_nodes = _bounded_int(
        _graph_config_value(feature, "max_expanded_nodes"),
        default=DEFAULT_GRAPH_MAX_EXPANDED_NODES,
        minimum=1,
        maximum=HARD_GRAPH_MAX_EXPANDED_NODES,
    )

    window_start = as_of - timedelta(seconds=int(feature.window_seconds))
    try:
        db.execute(
            text("SELECT set_config('statement_timeout', :timeout_ms, true)"),
            {"timeout_ms": str(FEATURE_STATEMENT_TIMEOUT_MS)},
        )
    except Exception as exc:
        raise FeatureResolutionError("Unable to apply feature query timeout") from exc

    seed_text_value = _jsonb_text_value(entity_value)
    if not seed_text_value:
        return FeatureComputationResult(
            value=0,
            matched_event_count=0,
            as_of=as_of,
            window_start=window_start,
            entity_value_hash=_entity_value_hash(entity_value),
        )

    seed = (str(feature.entity), _graph_entity_value_hash(seed_text_value))
    frontier = {seed}
    visited_entities = {seed}
    visited_event_ids: set[int] = set()
    target_entities: set[tuple[str, str]] = set()
    expanded_nodes = 1

    for _ in range(max_depth):
        if not frontier:
            break

        candidate_event_rows = (
            db.query(GraphEventEntityLink.ev_id, GraphEventEntityLink.transaction_id)
            .join(EventVersion, EventVersion.ev_id == GraphEventEntityLink.ev_id)
            .filter(
                GraphEventEntityLink.o_id == o_id,
                GraphEventEntityLink.effective_at >= window_start,
                GraphEventEntityLink.effective_at < as_of,
                EventVersion.observed_at <= as_of,
                tuple_(GraphEventEntityLink.entity_type, GraphEventEntityLink.entity_value_hash).in_(list(frontier)),
            )
            .distinct()
            .limit(max_expanded_nodes + 1)
            .all()
        )
        candidate_event_ids = {int(row.ev_id) for row in candidate_event_rows}
        candidate_transaction_ids = {str(row.transaction_id) for row in candidate_event_rows}
        current_event_ids = _current_event_version_ids_as_of(db, o_id, candidate_transaction_ids, as_of)
        event_ids = (candidate_event_ids & current_event_ids) - visited_event_ids
        if not event_ids:
            break
        expanded_nodes += len(event_ids)
        if expanded_nodes > max_expanded_nodes:
            raise FeatureResolutionError("Graph feature expansion cap exceeded")
        visited_event_ids.update(event_ids)

        link_rows = (
            db.query(GraphEventEntityLink.entity_type, GraphEventEntityLink.entity_value_hash)
            .filter(
                GraphEventEntityLink.o_id == o_id,
                GraphEventEntityLink.ev_id.in_(event_ids),
                GraphEventEntityLink.entity_type.in_(allowed_entity_types),
            )
            .limit(max_expanded_nodes + 1)
            .all()
        )
        if len(link_rows) > max_expanded_nodes:
            raise FeatureResolutionError("Graph feature expansion cap exceeded")

        next_frontier: set[tuple[str, str]] = set()
        for row in link_rows:
            entity = (str(row.entity_type), str(row.entity_value_hash))
            if entity[0] == target_entity:
                target_entities.add(entity)
            if entity not in visited_entities:
                visited_entities.add(entity)
                next_frontier.add(entity)

        expanded_nodes += len(next_frontier)
        if expanded_nodes > max_expanded_nodes:
            raise FeatureResolutionError("Graph feature expansion cap exceeded")
        frontier = next_frontier

    return FeatureComputationResult(
        value=len(target_entities),
        matched_event_count=len(visited_event_ids),
        as_of=as_of,
        window_start=window_start,
        entity_value_hash=_entity_value_hash(entity_value),
    )


def compute_feature(
    db: Any,
    o_id: int,
    feature: FeatureDefinition,
    event_data: dict[str, Any],
    as_of: datetime,
) -> FeatureComputationResult:
    if str(feature.feature_kind) == "graph":
        if str(feature.aggregation_type) != FeatureAggregation.GRAPH_DISTINCT_COUNT.value:
            raise FeatureResolutionError(f"Unsupported graph feature aggregation '{feature.aggregation_type}'")
        return _compute_graph_distinct_count(db, o_id, feature, event_data, as_of)
    return _compute_aggregate_feature(db, o_id, feature, event_data, as_of)


class FeatureResolver:
    def __init__(self, db: Any, o_id: int):
        self.db = db
        self.o_id = o_id
        self._cache: dict[tuple[str, str, datetime], FeatureComputationResult] = {}
        self.last_resolution_traces: list[FeatureResolutionTrace] = []

    def resolve(self, event_data: dict[str, Any], as_of: datetime, stat_paths: set[str]) -> dict[str, Any]:
        resolved, _ = self.resolve_with_traces(event_data, as_of, stat_paths)
        return resolved

    def resolve_with_traces(
        self, event_data: dict[str, Any], as_of: datetime, stat_paths: set[str]
    ) -> tuple[dict[str, Any], list[FeatureResolutionTrace]]:
        self.last_resolution_traces = []
        validate_feature_reference_budget(stat_paths)
        if not stat_paths:
            return {}, []

        features = (
            self.db.query(FeatureDefinition)
            .filter(
                FeatureDefinition.o_id == self.o_id,
                FeatureDefinition.status == "active",
            )
            .all()
        )
        by_path = {feature_path(feature): feature for feature in features}
        missing = sorted(stat_path for stat_path in stat_paths if stat_path not in by_path)
        if missing:
            raise FeatureResolutionError(f"Unknown or inactive computed stats: {', '.join(missing)}")

        resolved: dict[str, Any] = {}
        traces: list[FeatureResolutionTrace] = []
        as_of = normalize_as_utc(as_of)
        for stat_path in sorted(stat_paths):
            feature = by_path[stat_path]
            entity_value = _safe_get(event_data, str(feature.entity_key))
            if entity_value is None:
                trace = FeatureResolutionTrace(
                    stat_path=stat_path,
                    feature_id=int(feature.fd_id) if feature.fd_id is not None else None,
                    feature_kind=str(feature.feature_kind),
                    feature_version=int(feature.version) if feature.version is not None else None,
                    as_of=as_of,
                    window_start=as_of,
                    matched_event_count=0,
                    entity_value_hash=None,
                    resolution_status="failed",
                    warning=f"Event is missing entity key '{feature.entity_key}' required for stat[{stat_path}]",
                )
                traces.append(trace)
                self.last_resolution_traces = traces
                raise FeatureResolutionError(
                    f"Event is missing entity key '{feature.entity_key}' required for stat[{stat_path}]"
                )
            entity_value = str(entity_value)
            cache_key = (stat_path, entity_value, as_of)
            if cache_key not in self._cache:
                self._cache[cache_key] = compute_feature(self.db, self.o_id, feature, event_data, as_of)
            result = self._cache[cache_key]
            resolved[stat_path] = result.value
            traces.append(
                FeatureResolutionTrace(
                    stat_path=stat_path,
                    feature_id=int(feature.fd_id) if feature.fd_id is not None else None,
                    feature_kind=str(feature.feature_kind),
                    feature_version=int(feature.version) if feature.version is not None else None,
                    as_of=result.as_of,
                    window_start=result.window_start,
                    matched_event_count=result.matched_event_count,
                    entity_value_hash=result.entity_value_hash,
                    resolution_status="resolved",
                )
            )
        self.last_resolution_traces = traces
        return resolved, traces

    def persist_traces(
        self,
        traces: list[FeatureResolutionTrace],
        *,
        evaluation_decision_id: int | None = None,
        backtest_task_id: str | None = None,
        backtest_record_index: int | None = None,
    ) -> None:
        for trace in traces:
            self.db.add(
                FeatureSnapshotResolution(
                    o_id=self.o_id,
                    ed_id=evaluation_decision_id,
                    backtest_task_id=backtest_task_id,
                    backtest_record_index=backtest_record_index,
                    fd_id=trace.feature_id,
                    stat_path=trace.stat_path,
                    feature_kind=trace.feature_kind,
                    feature_version=trace.feature_version,
                    as_of=trace.as_of,
                    window_start=trace.window_start,
                    matched_event_count=trace.matched_event_count,
                    entity_value_hash=trace.entity_value_hash,
                    resolution_status=trace.resolution_status,
                    warning=trace.warning,
                )
            )


def summarize_feature_snapshot_resolutions(db: Any, o_id: int, backtest_task_id: str) -> dict[str, Any]:
    rows = (
        db.query(FeatureSnapshotResolution)
        .filter(
            FeatureSnapshotResolution.o_id == o_id,
            FeatureSnapshotResolution.backtest_task_id == backtest_task_id,
        )
        .order_by(FeatureSnapshotResolution.stat_path.asc(), FeatureSnapshotResolution.as_of.asc())
        .all()
    )
    if not rows:
        return {"feature_snapshots": [], "feature_snapshot_warnings": []}

    grouped: dict[str, list[FeatureSnapshotResolution]] = defaultdict(list)
    for row in rows:
        grouped[str(row.stat_path)].append(row)

    snapshots: list[dict[str, Any]] = []
    warnings: list[str] = []
    for stat_path in sorted(grouped):
        stat_rows = grouped[stat_path]
        status_counts = Counter(str(row.resolution_status) for row in stat_rows)
        warning_count = sum(1 for row in stat_rows if row.warning)
        warnings.extend(str(row.warning) for row in stat_rows if row.warning)
        matched_counts = [int(row.matched_event_count or 0) for row in stat_rows]
        snapshots.append(
            {
                "stat_path": stat_path,
                "feature_id": int(stat_rows[0].fd_id) if stat_rows[0].fd_id is not None else None,
                "feature_kind": stat_rows[0].feature_kind,
                "feature_version": int(stat_rows[0].feature_version)
                if stat_rows[0].feature_version is not None
                else None,
                "as_of_start": min(normalize_as_utc(cast(datetime, row.as_of)) for row in stat_rows).isoformat(),
                "as_of_end": max(normalize_as_utc(cast(datetime, row.as_of)) for row in stat_rows).isoformat(),
                "window_start": min(
                    normalize_as_utc(cast(datetime, row.window_start)) for row in stat_rows
                ).isoformat(),
                "matched_event_count_min": min(matched_counts),
                "matched_event_count_max": max(matched_counts),
                "resolution_status_counts": dict(sorted(status_counts.items())),
                "warning_count": warning_count,
            }
        )
    return {
        "feature_snapshots": snapshots,
        "feature_snapshot_warnings": sorted(set(warnings)),
    }
