"""Deterministic analysis helpers exposed through agent-tool API routes."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.orm import aliased

from ezrules.backend.features import FeatureResolutionError, FeatureResolver
from ezrules.backend.utils import load_cast_configs
from ezrules.core.field_paths import get_field_value
from ezrules.core.rule import MissingFieldLookupError, MissingStatLookupError, Rule, RuleFactory
from ezrules.core.type_casting import CastError, RequiredFieldError, find_missing_fields, normalize_event
from ezrules.core.user_lists import PersistentUserListManager
from ezrules.models.backend_core import EvaluationDecision, EventVersion, EventVersionLabel, Label
from ezrules.models.backend_core import Rule as RuleModel

NO_OUTCOME = "NO_OUTCOME"
DEFAULT_NEGATIVE_LABELS = ("NORMAL", "LEGIT", "GENUINE")
DEFAULT_POSITIVE_LABELS = ("FRAUD",)


@dataclass(slots=True)
class AgentToolRecord:
    transaction_id: str
    event_version: int
    evaluation_decision_id: int
    event_data: dict[str, Any]
    effective_at: datetime
    evaluated_at: datetime
    label_name: str | None


@dataclass(slots=True)
class ReplayEvaluation:
    record: AgentToolRecord
    stored_outcome: str | None
    proposed_outcome: str | None
    group_values: dict[str, Any]
    event_data_snippet: dict[str, Any]


@dataclass(slots=True)
class ReplayResult:
    total_records: int
    eligible_records: int
    skipped_records: int
    stored_counts: Counter[str]
    proposed_counts: Counter[str]
    evaluations: list[ReplayEvaluation]
    warnings: list[str]


def _lookback_start(lookback_days: int) -> datetime:
    return datetime.now(UTC) - timedelta(days=lookback_days)


def _safe_outcome(value: Any) -> str | None:
    return str(value) if value is not None else None


def _count_key(outcome: str | None) -> str:
    return outcome if outcome is not None else NO_OUTCOME


def _sorted_counts(counter: Counter[str]) -> dict[str, int]:
    return {key: counter[key] for key in sorted(counter)}


def _outcome_delta(stored: Counter[str], proposed: Counter[str]) -> dict[str, int]:
    keys = sorted(set(stored) | set(proposed))
    return {key: proposed[key] - stored[key] for key in keys if proposed[key] != stored[key]}


def _field_value_or_none(event_data: dict[str, Any], field_path: str) -> Any:
    try:
        return get_field_value(event_data, field_path)
    except KeyError:
        return None


def _event_snippet(event_data: dict[str, Any], field_paths: Iterable[str]) -> dict[str, Any]:
    snippet: dict[str, Any] = {}
    for field_path in sorted(set(field_paths)):
        snippet[field_path] = _field_value_or_none(event_data, field_path)
    if snippet:
        return snippet

    for key in sorted(event_data)[:8]:
        value = event_data[key]
        if isinstance(value, dict | list):
            continue
        snippet[str(key)] = value
    return snippet


def _load_rule(db: Any, *, org_id: int, rule_id: int) -> RuleModel | None:
    return db.query(RuleModel).filter(RuleModel.r_id == rule_id, RuleModel.o_id == org_id).first()


def _compile_rules(
    db: Any,
    *,
    org_id: int,
    rule_model: RuleModel,
    proposed_logic: str | None,
) -> tuple[Rule, Rule | None]:
    list_provider = PersistentUserListManager(db_session=db, o_id=org_id)
    stored_rule = RuleFactory.from_json(rule_model.__dict__, list_values_provider=list_provider)
    proposed_rule = None
    if proposed_logic is not None:
        proposed_rule = Rule(rid="", logic=proposed_logic, list_values_provider=list_provider)
    return stored_rule, proposed_rule


def _load_recent_records(
    db: Any,
    *,
    org_id: int,
    lookback_days: int,
    max_records: int,
) -> list[AgentToolRecord]:
    label_alias = aliased(Label)
    rows = (
        db.query(
            EventVersion.transaction_id,
            EventVersion.event_version,
            EventVersion.event_data,
            EventVersion.effective_at,
            EvaluationDecision.ed_id,
            EvaluationDecision.evaluated_at,
            label_alias.label,
        )
        .join(EvaluationDecision, EvaluationDecision.ev_id == EventVersion.ev_id)
        .outerjoin(
            EventVersionLabel,
            (EventVersionLabel.ev_id == EventVersion.ev_id) & (EventVersionLabel.o_id == org_id),
        )
        .outerjoin(label_alias, (label_alias.el_id == EventVersionLabel.el_id) & (label_alias.o_id == org_id))
        .filter(
            EvaluationDecision.o_id == org_id,
            EvaluationDecision.served.is_(True),
            EvaluationDecision.decision_type == "served",
            EvaluationDecision.evaluated_at >= _lookback_start(lookback_days),
        )
        .order_by(EvaluationDecision.evaluated_at.desc(), EvaluationDecision.ed_id.desc())
        .limit(max_records)
        .all()
    )

    return [
        AgentToolRecord(
            transaction_id=str(row.transaction_id),
            event_version=int(row.event_version),
            evaluation_decision_id=int(row.ed_id),
            event_data=dict(row.event_data or {}),
            effective_at=row.effective_at if row.effective_at.tzinfo else row.effective_at.replace(tzinfo=UTC),
            evaluated_at=row.evaluated_at if row.evaluated_at.tzinfo else row.evaluated_at.replace(tzinfo=UTC),
            label_name=str(row.label) if row.label else None,
        )
        for row in rows
    ]


def replay_rule_change(
    db: Any,
    *,
    org_id: int,
    rule_model: RuleModel,
    proposed_logic: str | None,
    lookback_days: int,
    group_by: list[str],
    max_records: int,
) -> ReplayResult:
    stored_rule, proposed_rule = _compile_rules(
        db,
        org_id=org_id,
        rule_model=rule_model,
        proposed_logic=proposed_logic,
    )
    comparison_rule = proposed_rule or stored_rule
    referenced_fields = sorted(stored_rule.get_rule_params() | comparison_rule.get_rule_params() | set(group_by))
    stat_paths = stored_rule.get_rule_stats() | comparison_rule.get_rule_stats()
    configs = load_cast_configs(db, org_id)
    feature_resolver = FeatureResolver(db, org_id) if stat_paths else None

    records = _load_recent_records(db, org_id=org_id, lookback_days=lookback_days, max_records=max_records)
    warnings: list[str] = []
    if len(records) == max_records:
        warnings.append(f"Analysis was capped at the most recent {max_records} served decision(s).")

    skipped_records = 0
    stored_counts: Counter[str] = Counter()
    proposed_counts: Counter[str] = Counter()
    evaluations: list[ReplayEvaluation] = []
    missing_field_counts: Counter[str] = Counter()
    normalization_failures: Counter[str] = Counter()
    stat_failures: Counter[str] = Counter()

    for record in records:
        raw_event = dict(record.event_data)
        missing_fields = find_missing_fields(raw_event, referenced_fields)
        if missing_fields:
            skipped_records += 1
            missing_field_counts.update(missing_fields)
            continue

        try:
            normalized_event = normalize_event(raw_event, configs)
        except (CastError, RequiredFieldError) as exc:
            skipped_records += 1
            normalization_failures[str(exc)] += 1
            continue

        stats: dict[str, Any] | None = None
        if stat_paths:
            try:
                assert feature_resolver is not None
                stats, _ = feature_resolver.resolve_with_traces(normalized_event, record.effective_at, stat_paths)
            except FeatureResolutionError as exc:
                skipped_records += 1
                stat_failures[str(exc)] += 1
                continue

        try:
            stored_outcome = _safe_outcome(stored_rule(normalized_event, stats))
            proposed_outcome = _safe_outcome(comparison_rule(normalized_event, stats))
        except MissingFieldLookupError as exc:
            skipped_records += 1
            missing_field_counts[exc.field_name] += 1
            continue
        except MissingStatLookupError as exc:
            skipped_records += 1
            stat_failures[exc.stat_path] += 1
            continue

        stored_counts[_count_key(stored_outcome)] += 1
        proposed_counts[_count_key(proposed_outcome)] += 1
        group_values = {field_path: _field_value_or_none(normalized_event, field_path) for field_path in group_by}
        evaluations.append(
            ReplayEvaluation(
                record=record,
                stored_outcome=stored_outcome,
                proposed_outcome=proposed_outcome,
                group_values=group_values,
                event_data_snippet=_event_snippet(normalized_event, referenced_fields),
            )
        )

    if missing_field_counts:
        warnings.append(
            "Records missing referenced fields were skipped: "
            + ", ".join(f"{field} ({missing_field_counts[field]})" for field in sorted(missing_field_counts))
            + "."
        )
    if normalization_failures:
        warnings.extend(
            f"Records excluded by normalization rules: {message} ({count})."
            for message, count in sorted(normalization_failures.items())
        )
    if stat_failures:
        warnings.append(
            "Records with unavailable computed stats were skipped: "
            + ", ".join(f"{reason} ({stat_failures[reason]})" for reason in sorted(stat_failures))
            + "."
        )

    return ReplayResult(
        total_records=len(records),
        eligible_records=len(evaluations),
        skipped_records=skipped_records,
        stored_counts=stored_counts,
        proposed_counts=proposed_counts,
        evaluations=evaluations,
        warnings=warnings,
    )


def build_blast_radius(
    db: Any,
    *,
    org_id: int,
    rule_id: int,
    proposed_logic: str,
    lookback_days: int,
    group_by: list[str],
    sample_limit: int,
    max_records: int,
) -> dict[str, Any] | None:
    rule_model = _load_rule(db, org_id=org_id, rule_id=rule_id)
    if rule_model is None:
        return None

    replay = replay_rule_change(
        db,
        org_id=org_id,
        rule_model=rule_model,
        proposed_logic=proposed_logic,
        lookback_days=lookback_days,
        group_by=group_by,
        max_records=max_records,
    )
    changed = [
        item for item in replay.evaluations if _count_key(item.stored_outcome) != _count_key(item.proposed_outcome)
    ]

    group_counters: dict[tuple[tuple[str, str], ...], dict[str, Any]] = {}
    for item in replay.evaluations:
        group_key = tuple(sorted((key, str(value)) for key, value in item.group_values.items()))
        group = group_counters.setdefault(
            group_key,
            {
                "group": dict(item.group_values),
                "total_records": 0,
                "changed_decision_count": 0,
                "stored_result": Counter(),
                "proposed_result": Counter(),
            },
        )
        group["total_records"] += 1
        group["stored_result"][_count_key(item.stored_outcome)] += 1
        group["proposed_result"][_count_key(item.proposed_outcome)] += 1
        if _count_key(item.stored_outcome) != _count_key(item.proposed_outcome):
            group["changed_decision_count"] += 1

    group_deltas = []
    for group in group_counters.values():
        stored_result = group["stored_result"]
        proposed_result = group["proposed_result"]
        group_deltas.append(
            {
                "group": group["group"],
                "total_records": group["total_records"],
                "changed_decision_count": group["changed_decision_count"],
                "changed_decision_rate": round(group["changed_decision_count"] / group["total_records"], 4)
                if group["total_records"]
                else 0.0,
                "stored_result": _sorted_counts(stored_result),
                "proposed_result": _sorted_counts(proposed_result),
                "outcome_delta": _outcome_delta(stored_result, proposed_result),
            }
        )
    group_deltas.sort(key=lambda row: (row["changed_decision_count"], row["total_records"]), reverse=True)

    return {
        "rule_id": rule_id,
        "lookback_days": lookback_days,
        "total_records": replay.total_records,
        "eligible_records": replay.eligible_records,
        "skipped_records": replay.skipped_records,
        "stored_result": _sorted_counts(replay.stored_counts),
        "proposed_result": _sorted_counts(replay.proposed_counts),
        "outcome_delta": _outcome_delta(replay.stored_counts, replay.proposed_counts),
        "changed_decision_count": len(changed),
        "changed_decision_rate": round(len(changed) / replay.eligible_records, 4) if replay.eligible_records else 0.0,
        "group_deltas": group_deltas,
        "flipped_events": [_evidence_row(item) for item in changed[:sample_limit]],
        "warnings": replay.warnings,
    }


def _outcome_is_actionable(outcome: str | None, target_outcomes: set[str] | None) -> bool:
    if outcome is None:
        return False
    return target_outcomes is None or outcome in target_outcomes


def _is_wrong(
    *,
    label_name: str | None,
    outcome: str | None,
    positive_labels: set[str],
    negative_labels: set[str],
    target_outcomes: set[str] | None,
) -> bool:
    if label_name is None:
        return False
    fired = _outcome_is_actionable(outcome, target_outcomes)
    if label_name in positive_labels:
        return not fired
    if label_name in negative_labels:
        return fired
    return False


def _evidence_row(item: ReplayEvaluation) -> dict[str, Any]:
    return {
        "transaction_id": item.record.transaction_id,
        "event_version": item.record.event_version,
        "evaluation_decision_id": item.record.evaluation_decision_id,
        "label_name": item.record.label_name,
        "stored_outcome": item.stored_outcome,
        "proposed_outcome": item.proposed_outcome,
        "group": item.group_values,
        "event_data": item.event_data_snippet,
    }


def build_rule_counterexamples(
    db: Any,
    *,
    org_id: int,
    rule_id: int,
    proposed_logic: str | None,
    lookback_days: int,
    positive_labels: list[str],
    negative_labels: list[str],
    target_outcomes: list[str] | None,
    sample_limit: int,
    max_records: int,
) -> dict[str, Any] | None:
    rule_model = _load_rule(db, org_id=org_id, rule_id=rule_id)
    if rule_model is None:
        return None

    replay = replay_rule_change(
        db,
        org_id=org_id,
        rule_model=rule_model,
        proposed_logic=proposed_logic,
        lookback_days=lookback_days,
        group_by=[],
        max_records=max_records,
    )
    positive_label_set = set(positive_labels or DEFAULT_POSITIVE_LABELS)
    negative_label_set = set(negative_labels or DEFAULT_NEGATIVE_LABELS)
    target_outcome_set = set(target_outcomes) if target_outcomes else None

    buckets: dict[str, list[dict[str, Any]]] = {
        "fired_but_negative": [],
        "missed_positive": [],
        "candidate_fixes_existing": [],
        "candidate_introduces_new_errors": [],
    }

    for item in replay.evaluations:
        label_name = item.record.label_name
        if label_name is None:
            continue

        stored_wrong = _is_wrong(
            label_name=label_name,
            outcome=item.stored_outcome,
            positive_labels=positive_label_set,
            negative_labels=negative_label_set,
            target_outcomes=target_outcome_set,
        )
        proposed_wrong = _is_wrong(
            label_name=label_name,
            outcome=item.proposed_outcome,
            positive_labels=positive_label_set,
            negative_labels=negative_label_set,
            target_outcomes=target_outcome_set,
        )

        fired = _outcome_is_actionable(item.stored_outcome, target_outcome_set)
        if label_name in negative_label_set and fired and len(buckets["fired_but_negative"]) < sample_limit:
            buckets["fired_but_negative"].append(_evidence_row(item))
        if label_name in positive_label_set and not fired and len(buckets["missed_positive"]) < sample_limit:
            buckets["missed_positive"].append(_evidence_row(item))
        if stored_wrong and not proposed_wrong and len(buckets["candidate_fixes_existing"]) < sample_limit:
            buckets["candidate_fixes_existing"].append(_evidence_row(item))
        if not stored_wrong and proposed_wrong and len(buckets["candidate_introduces_new_errors"]) < sample_limit:
            buckets["candidate_introduces_new_errors"].append(_evidence_row(item))

    return {
        "rule_id": rule_id,
        "lookback_days": lookback_days,
        "total_records": replay.total_records,
        "eligible_records": replay.eligible_records,
        "skipped_records": replay.skipped_records,
        "positive_labels": sorted(positive_label_set),
        "negative_labels": sorted(negative_label_set),
        "target_outcomes": sorted(target_outcome_set) if target_outcome_set is not None else None,
        "buckets": buckets,
        "warnings": replay.warnings,
    }
