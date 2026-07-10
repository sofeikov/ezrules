"""Shared rule-quality metric computation for API and async report jobs."""

from __future__ import annotations

import datetime
import hashlib
from collections import defaultdict
from typing import Any

import sqlalchemy
from sqlalchemy.dialects.postgresql import JSONB

from ezrules.backend.quality_metrics import compute_quality_metric_values
from ezrules.models.backend_core import (
    EvaluationDecision,
    EvaluationRuleResult,
    EventVersionLabel,
    Label,
    RuleQualityPair,
)
from ezrules.models.backend_core import Rule as RuleModel


def _safe_round(value: float | None) -> float | None:
    return round(value, 4) if value is not None else None


def _format_pair(metric: dict[str, Any]) -> str:
    return f"{metric['outcome']} -> {metric['label']}"


def normalize_rule_quality_pairs(
    curated_pairs: list[tuple[str, str]],
) -> list[tuple[str, str]]:
    unique_pairs = {
        (outcome.strip(), label.strip())
        for outcome, label in curated_pairs
        if outcome and label and outcome.strip() and label.strip()
    }
    return sorted(unique_pairs, key=lambda pair: (pair[0], pair[1]))


def compute_rule_quality_pairs_hash(curated_pairs: list[tuple[str, str]]) -> str:
    normalized = normalize_rule_quality_pairs(curated_pairs)
    payload = "\n".join(f"{outcome}|{label}" for outcome, label in normalized)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def get_active_rule_quality_pairs(
    db: Any,
    *,
    o_id: int | None,
) -> list[tuple[str, str]]:
    query = db.query(RuleQualityPair).filter(RuleQualityPair.active.is_(True))
    if o_id is not None:
        query = query.filter(RuleQualityPair.o_id == o_id)
    pairs = [(str(item.outcome), str(item.label)) for item in query.all()]
    return normalize_rule_quality_pairs(pairs)


def get_rule_quality_snapshot_max_decision_id(
    db: Any,
    *,
    freeze_at: datetime.datetime,
    o_id: int | None,
) -> int:
    """Return upper decision-id bound for a stable snapshot at freeze_at."""
    query = db.query(sqlalchemy.func.max(EvaluationDecision.ed_id)).filter(
        EvaluationDecision.evaluated_at <= freeze_at,
        EvaluationDecision.served.is_(True),
        EvaluationDecision.decision_type == "served",
    )
    if o_id is not None:
        query = query.filter(EvaluationDecision.o_id == o_id)
    max_decision_id = query.scalar()
    return int(max_decision_id or 0)


def compute_rule_quality_metrics(
    db: Any,
    *,
    min_support: int,
    lookback_days: int,
    freeze_at: datetime.datetime,
    max_decision_id: int | None,
    o_id: int | None,
    curated_pairs: list[tuple[str, str]],
) -> dict[str, Any]:
    """Compute precision/recall metrics for outcome->label pairs."""
    start_time = freeze_at - datetime.timedelta(days=lookback_days)
    selected_pairs = normalize_rule_quality_pairs(curated_pairs)
    raw_all_rule_results = sqlalchemy.cast(EvaluationDecision.all_rule_results, JSONB)
    has_complete_rule_results = sqlalchemy.func.jsonb_typeof(raw_all_rule_results) == "object"
    safe_all_rule_results = sqlalchemy.case(
        (has_complete_rule_results, raw_all_rule_results),
        else_=sqlalchemy.cast(sqlalchemy.literal("{}"), JSONB),
    )

    base_filters: list[Any] = [
        EvaluationDecision.served.is_(True),
        EvaluationDecision.decision_type == "served",
        EvaluationDecision.evaluated_at >= start_time,
        EvaluationDecision.evaluated_at <= freeze_at,
        has_complete_rule_results,
        EventVersionLabel.assigned_at <= freeze_at,
    ]
    if max_decision_id is not None and max_decision_id > 0:
        base_filters.append(EvaluationDecision.ed_id <= max_decision_id)
    if o_id is not None:
        base_filters.append(EvaluationDecision.o_id == o_id)

    label_count_rows = (
        db.query(
            Label.label,
            sqlalchemy.func.count(sqlalchemy.func.distinct(EvaluationDecision.ed_id)).label("count"),
        )
        .join(EventVersionLabel, EventVersionLabel.ev_id == EvaluationDecision.ev_id)
        .join(Label, Label.el_id == EventVersionLabel.el_id)
        .filter(*base_filters)
        .filter(EventVersionLabel.o_id == o_id if o_id is not None else sqlalchemy.true())
        .filter(Label.o_id == o_id if o_id is not None else sqlalchemy.true())
        .group_by(Label.label)
        .all()
    )
    total_labeled_events = sum(int(count) for _label_name, count in label_count_rows)

    if not selected_pairs:
        return {
            "total_labeled_events": total_labeled_events,
            "min_support": min_support,
            "lookback_days": lookback_days,
            "freeze_at": freeze_at,
            "pair_metrics": [],
            "best_rules": [],
            "worst_rules": [],
        }

    expanded_results = sqlalchemy.func.jsonb_each(safe_all_rule_results).table_valued("key", "value").lateral()
    grouped_rows = (
        db.query(
            EvaluationRuleResult.r_id,
            RuleModel.rid,
            RuleModel.description,
            EvaluationRuleResult.rule_result,
            Label.label,
            sqlalchemy.func.count(sqlalchemy.func.distinct(EvaluationDecision.ed_id)).label("count"),
        )
        .join(EvaluationDecision, EvaluationDecision.ed_id == EvaluationRuleResult.ed_id)
        .join(expanded_results, sqlalchemy.cast(EvaluationRuleResult.r_id, sqlalchemy.String) == expanded_results.c.key)
        .join(EventVersionLabel, EventVersionLabel.ev_id == EvaluationDecision.ev_id)
        .join(Label, Label.el_id == EventVersionLabel.el_id)
        .join(RuleModel, RuleModel.r_id == EvaluationRuleResult.r_id)
        .filter(*base_filters)
        .filter(EventVersionLabel.o_id == o_id if o_id is not None else sqlalchemy.true())
        .filter(Label.o_id == o_id if o_id is not None else sqlalchemy.true())
        .group_by(
            EvaluationRuleResult.r_id,
            RuleModel.rid,
            RuleModel.description,
            EvaluationRuleResult.rule_result,
            Label.label,
        )
        .all()
    )

    exposure_rows = (
        db.query(
            RuleModel.r_id,
            RuleModel.rid,
            RuleModel.description,
            Label.label,
            sqlalchemy.func.count(sqlalchemy.func.distinct(EvaluationDecision.ed_id)).label("count"),
        )
        .select_from(EvaluationDecision)
        .join(expanded_results, sqlalchemy.true())
        .join(RuleModel, sqlalchemy.cast(RuleModel.r_id, sqlalchemy.String) == expanded_results.c.key)
        .join(EventVersionLabel, EventVersionLabel.ev_id == EvaluationDecision.ev_id)
        .join(Label, Label.el_id == EventVersionLabel.el_id)
        .filter(*base_filters)
        .filter(EventVersionLabel.o_id == o_id if o_id is not None else sqlalchemy.true())
        .filter(Label.o_id == o_id if o_id is not None else sqlalchemy.true())
        .group_by(RuleModel.r_id, RuleModel.rid, RuleModel.description, Label.label)
        .all()
    )

    rule_meta: dict[int, tuple[str, str]] = {}
    rule_matrix: dict[int, dict[tuple[str, str], int]] = defaultdict(dict)
    evaluated_label_totals: dict[int, dict[str, int]] = defaultdict(dict)
    outcomes_by_rule: dict[int, set[str]] = defaultdict(set)
    labels_by_rule: dict[int, set[str]] = defaultdict(set)

    for r_id, rid, description, label_name, count in exposure_rows:
        rule_meta[r_id] = (rid, description)
        evaluated_label_totals[r_id][label_name] = count
        labels_by_rule[r_id].add(label_name)

    for r_id, rid, description, outcome, label_name, count in grouped_rows:
        rule_meta[r_id] = (rid, description)
        rule_matrix[r_id][(outcome, label_name)] = count
        outcomes_by_rule[r_id].add(outcome)
        labels_by_rule[r_id].add(label_name)

    pair_metrics: list[dict[str, Any]] = []
    summaries: list[dict[str, Any]] = []

    for r_id in sorted(rule_meta.keys(), key=lambda key: rule_meta[key][0]):
        rid, description = rule_meta[r_id]
        outcomes = sorted(outcomes_by_rule[r_id])
        labels = sorted(labels_by_rule[r_id])
        matrix = rule_matrix[r_id]

        outcome_totals = {outcome: sum(matrix.get((outcome, label), 0) for label in labels) for outcome in outcomes}
        rule_pairs: list[dict[str, Any]] = []
        for outcome, label_name in selected_pairs:
            predicted_positives = outcome_totals.get(outcome, 0)
            actual_positives = evaluated_label_totals[r_id].get(label_name, 0)
            if predicted_positives < min_support and actual_positives < min_support:
                continue

            values = compute_quality_metric_values(
                true_positive=matrix.get((outcome, label_name), 0),
                predicted_positives=predicted_positives,
                actual_positives=actual_positives,
            )

            metric = {
                "r_id": r_id,
                "rid": rid,
                "description": description,
                "outcome": outcome,
                "label": label_name,
                "true_positive": values["true_positive"],
                "false_positive": values["false_positive"],
                "false_negative": values["false_negative"],
                "predicted_positives": values["predicted_positives"],
                "actual_positives": values["actual_positives"],
                "precision": _safe_round(values["precision"]),
                "recall": _safe_round(values["recall"]),
                "f1": _safe_round(values["f1"]),
            }
            pair_metrics.append(metric)
            rule_pairs.append(metric)

        precisions = [metric["precision"] for metric in rule_pairs if metric["precision"] is not None]
        recalls = [metric["recall"] for metric in rule_pairs if metric["recall"] is not None]
        f1_scores = [metric["f1"] for metric in rule_pairs if metric["f1"] is not None]

        average_precision = sum(precisions) / len(precisions) if precisions else None
        average_recall = sum(recalls) / len(recalls) if recalls else None
        average_f1 = sum(f1_scores) / len(f1_scores) if f1_scores else None

        scored_pairs = sorted(
            (metric for metric in rule_pairs if metric["f1"] is not None),
            key=lambda metric: metric["f1"] or 0,
            reverse=True,
        )
        best_pair = _format_pair(scored_pairs[0]) if scored_pairs else None
        worst_pair = _format_pair(scored_pairs[-1]) if scored_pairs else None

        summaries.append(
            {
                "r_id": r_id,
                "rid": rid,
                "description": description,
                "labeled_events": sum(evaluated_label_totals[r_id].values()),
                "pair_count": len(rule_pairs),
                "average_precision": _safe_round(average_precision),
                "average_recall": _safe_round(average_recall),
                "average_f1": _safe_round(average_f1),
                "best_pair": best_pair,
                "worst_pair": worst_pair,
            }
        )

    pair_metrics.sort(key=lambda metric: (metric["rid"], metric["outcome"], metric["label"]))

    # Only rank rules that produced at least one scored pair. Otherwise the
    # summary tables fill with N/A rows when a curated pair never fires.
    ranked_summaries = [summary for summary in summaries if summary["average_f1"] is not None]
    best_rules = sorted(
        ranked_summaries,
        key=lambda summary: summary["average_f1"] if summary["average_f1"] is not None else -1.0,
        reverse=True,
    )[:5]
    worst_rules = sorted(
        ranked_summaries,
        key=lambda summary: summary["average_f1"] if summary["average_f1"] is not None else 2.0,
    )[:5]

    return {
        "total_labeled_events": total_labeled_events,
        "min_support": min_support,
        "lookback_days": lookback_days,
        "freeze_at": freeze_at,
        "pair_metrics": pair_metrics,
        "best_rules": best_rules,
        "worst_rules": worst_rules,
    }
