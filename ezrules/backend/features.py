from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy import text

from ezrules.backend.api_v2.schemas.features import ALLOWED_WINDOW_SECONDS, FeatureAggregation
from ezrules.core.field_paths import get_field_value
from ezrules.core.rule_helpers import StatReferenceExtractor
from ezrules.models.backend_core import EventVersion, FeatureDefinition
from ezrules.models.backend_core import Rule as RuleModel

MAX_STAT_REFERENCES_PER_RULE = 10
MAX_ACTIVE_FEATURES_PER_ORG = 100
FEATURE_STATEMENT_TIMEOUT_MS = 750


class FeatureResolutionError(Exception):
    """Raised when a referenced stat cannot be resolved for rule evaluation."""


@dataclass(frozen=True)
class FeatureComputationResult:
    value: Any
    matched_event_count: int
    as_of: datetime
    window_start: datetime


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
    return (
        db.query(RuleModel)
        .filter(RuleModel.o_id == o_id, RuleModel.logic.contains(token))
        .order_by(RuleModel.r_id.asc())
        .all()
    )


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


def compute_feature(
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
        db.execute(text("SET LOCAL statement_timeout = :timeout_ms"), {"timeout_ms": FEATURE_STATEMENT_TIMEOUT_MS})
    except Exception:
        pass

    candidates = (
        db.query(EventVersion)
        .filter(
            EventVersion.o_id == o_id,
            EventVersion.effective_at >= window_start,
            EventVersion.effective_at < as_of,
        )
        .order_by(EventVersion.effective_at.asc(), EventVersion.ev_id.asc())
        .all()
    )
    filters = list(cast(list[dict[str, Any]], feature.filters or []))
    matched_events = [
        event
        for event in candidates
        if _safe_get(cast(dict[str, Any], event.event_data), str(feature.entity_key)) == entity_value
        and _filter_matches(cast(dict[str, Any], event.event_data), filters)
    ]
    return FeatureComputationResult(
        value=_compute_aggregate(feature, matched_events, as_of=as_of),
        matched_event_count=len(matched_events),
        as_of=as_of,
        window_start=window_start,
    )


class FeatureResolver:
    def __init__(self, db: Any, o_id: int):
        self.db = db
        self.o_id = o_id
        self._cache: dict[tuple[str, str, datetime], Any] = {}

    def resolve(self, event_data: dict[str, Any], as_of: datetime, stat_paths: set[str]) -> dict[str, Any]:
        validate_feature_reference_budget(stat_paths)
        if not stat_paths:
            return {}

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
        as_of = normalize_as_utc(as_of)
        for stat_path in sorted(stat_paths):
            feature = by_path[stat_path]
            entity_value = str(_safe_get(event_data, str(feature.entity_key)))
            cache_key = (stat_path, entity_value, as_of)
            if cache_key not in self._cache:
                self._cache[cache_key] = compute_feature(self.db, self.o_id, feature, event_data, as_of).value
            resolved[stat_path] = self._cache[cache_key]
        return resolved
