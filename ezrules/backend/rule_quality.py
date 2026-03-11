"""Shared rule-quality metric computation for API and async report jobs."""

from __future__ import annotations

import datetime
import hashlib
from collections import defaultdict
from typing import Any

import sqlalchemy

from ezrules.models.backend_core import Label, RuleQualityPair, TestingRecordLog, TestingResultsLog
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


def get_rule_quality_snapshot_max_tl_id(
    db: Any,
    *,
    freeze_at: datetime.datetime,
    o_id: int | None,
) -> int:
    """Return upper tl_id bound for a stable snapshot at freeze_at."""
    query = db.query(sqlalchemy.func.max(TestingRecordLog.tl_id)).filter(
        TestingRecordLog.created_at <= freeze_at,
    )
    if o_id is not None:
        query = query.filter(TestingRecordLog.o_id == o_id)
    max_tl_id = query.scalar()
    return int(max_tl_id or 0)


def compute_rule_quality_metrics(
    db: Any,
    *,
    min_support: int,
    lookback_days: int,
    freeze_at: datetime.datetime,
    max_tl_id: int | None,
    o_id: int | None,
    curated_pairs: list[tuple[str, str]],
) -> dict[str, Any]:
    """Compute precision/recall metrics for outcome->label pairs."""
    start_time = freeze_at - datetime.timedelta(days=lookback_days)
    selected_pairs = normalize_rule_quality_pairs(curated_pairs)

    base_filters: list[Any] = [
        TestingRecordLog.el_id.isnot(None),
        TestingRecordLog.created_at >= start_time,
        TestingRecordLog.created_at <= freeze_at,
    ]
    if max_tl_id is not None and max_tl_id > 0:
        base_filters.append(TestingRecordLog.tl_id <= max_tl_id)
    if o_id is not None:
        base_filters.append(TestingRecordLog.o_id == o_id)

    total_labeled_events = db.query(sqlalchemy.func.count(TestingRecordLog.tl_id)).filter(*base_filters).scalar() or 0

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

    grouped_rows = (
        db.query(
            TestingResultsLog.r_id,
            RuleModel.rid,
            RuleModel.description,
            TestingResultsLog.rule_result,
            Label.label,
            sqlalchemy.func.count(TestingResultsLog.tr_id).label("count"),
        )
        .join(TestingRecordLog, TestingRecordLog.tl_id == TestingResultsLog.tl_id)
        .join(Label, Label.el_id == TestingRecordLog.el_id)
        .join(RuleModel, RuleModel.r_id == TestingResultsLog.r_id)
        .filter(*base_filters)
        .group_by(
            TestingResultsLog.r_id,
            RuleModel.rid,
            RuleModel.description,
            TestingResultsLog.rule_result,
            Label.label,
        )
        .all()
    )

    rule_meta: dict[int, tuple[str, str]] = {}
    rule_matrix: dict[int, dict[tuple[str, str], int]] = defaultdict(dict)
    outcomes_by_rule: dict[int, set[str]] = defaultdict(set)
    labels_by_rule: dict[int, set[str]] = defaultdict(set)

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
        label_totals = {
            label_name: sum(matrix.get((outcome, label_name), 0) for outcome in outcomes) for label_name in labels
        }

        rule_pairs: list[dict[str, Any]] = []
        for outcome, label_name in selected_pairs:
            predicted_positives = outcome_totals.get(outcome, 0)
            actual_positives = label_totals.get(label_name, 0)
            if predicted_positives < min_support and actual_positives < min_support:
                continue

            true_positive = matrix.get((outcome, label_name), 0)
            false_positive = predicted_positives - true_positive
            false_negative = actual_positives - true_positive

            precision = true_positive / predicted_positives if predicted_positives > 0 else None
            recall = true_positive / actual_positives if actual_positives > 0 else None
            f1 = None
            if precision is not None and recall is not None and (precision + recall) > 0:
                f1 = 2 * precision * recall / (precision + recall)

            metric = {
                "r_id": r_id,
                "rid": rid,
                "description": description,
                "outcome": outcome,
                "label": label_name,
                "true_positive": true_positive,
                "false_positive": false_positive,
                "false_negative": false_negative,
                "predicted_positives": predicted_positives,
                "actual_positives": actual_positives,
                "precision": _safe_round(precision),
                "recall": _safe_round(recall),
                "f1": _safe_round(f1),
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
                "labeled_events": sum(outcome_totals.values()),
                "pair_count": len(rule_pairs),
                "average_precision": _safe_round(average_precision),
                "average_recall": _safe_round(average_recall),
                "average_f1": _safe_round(average_f1),
                "best_pair": best_pair,
                "worst_pair": worst_pair,
            }
        )

    pair_metrics.sort(key=lambda metric: (metric["rid"], metric["outcome"], metric["label"]))

    ranked_summaries = [summary for summary in summaries if summary["pair_count"] > 0]
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
