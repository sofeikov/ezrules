"""Helpers for computing backtest outcome and label-quality summaries."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from ezrules.models.backend_core import TestingRecordLog


def _safe_round(value: float | None) -> float | None:
    return round(value, 4) if value is not None else None


def _format_pair(outcome: str, label: str) -> str:
    return f"{outcome} -> {label}"


def _sorted_counts(counter: Counter[str]) -> dict[str, int]:
    return {key: counter[key] for key in sorted(counter)}


def _count_rates(counts: Counter[str], total_records: int) -> dict[str, float]:
    if total_records <= 0:
        return {}
    return {key: round((100 * counts[key] / total_records), 4) for key in sorted(counts)}


@dataclass
class _RuleMetricsAccumulator:
    outcome_counts: Counter[str] = field(default_factory=Counter)
    labeled_outcome_counts: Counter[str] = field(default_factory=Counter)
    outcome_label_counts: Counter[tuple[str, str]] = field(default_factory=Counter)

    def record(self, outcome: str | None, label: str | None) -> None:
        if outcome is None:
            return

        self.outcome_counts[outcome] += 1
        if label is None:
            return

        self.labeled_outcome_counts[outcome] += 1
        self.outcome_label_counts[(outcome, label)] += 1


def _build_quality_metrics(
    *,
    outcomes: list[str],
    labels: list[str],
    accumulator: _RuleMetricsAccumulator,
    label_counts: Counter[str],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    metrics: list[dict[str, Any]] = []

    for outcome in outcomes:
        predicted_positives = accumulator.labeled_outcome_counts.get(outcome, 0)
        for label in labels:
            actual_positives = label_counts.get(label, 0)
            if actual_positives <= 0:
                continue

            true_positive = accumulator.outcome_label_counts.get((outcome, label), 0)
            false_positive = predicted_positives - true_positive
            false_negative = actual_positives - true_positive

            precision = true_positive / predicted_positives if predicted_positives > 0 else None
            recall = true_positive / actual_positives if actual_positives > 0 else None

            f1 = None
            if precision is not None and recall is not None:
                if (precision + recall) > 0:
                    f1 = 2 * precision * recall / (precision + recall)
                else:
                    f1 = 0.0

            metrics.append(
                {
                    "outcome": outcome,
                    "label": label,
                    "true_positive": true_positive,
                    "false_positive": false_positive,
                    "false_negative": false_negative,
                    "predicted_positives": predicted_positives,
                    "actual_positives": actual_positives,
                    "precision": _safe_round(precision),
                    "recall": _safe_round(recall),
                    "f1": _safe_round(f1),
                }
            )

    active_metrics = [metric for metric in metrics if metric["predicted_positives"] > 0]

    precisions = [metric["precision"] for metric in active_metrics if metric["precision"] is not None]
    recalls = [metric["recall"] for metric in active_metrics if metric["recall"] is not None]
    f1_scores = [metric["f1"] for metric in active_metrics if metric["f1"] is not None]

    average_precision = sum(precisions) / len(precisions) if precisions else None
    average_recall = sum(recalls) / len(recalls) if recalls else None
    average_f1 = sum(f1_scores) / len(f1_scores) if f1_scores else None

    scored_pairs = sorted(
        (metric for metric in active_metrics if metric["f1"] is not None),
        key=lambda metric: (
            metric["f1"] if metric["f1"] is not None else -1.0,
            metric["outcome"],
            metric["label"],
        ),
        reverse=True,
    )
    best_pair = _format_pair(scored_pairs[0]["outcome"], scored_pairs[0]["label"]) if scored_pairs else None
    worst_pair = _format_pair(scored_pairs[-1]["outcome"], scored_pairs[-1]["label"]) if scored_pairs else None

    return metrics, {
        "pair_count": len(active_metrics),
        "average_precision": _safe_round(average_precision),
        "average_recall": _safe_round(average_recall),
        "average_f1": _safe_round(average_f1),
        "best_pair": best_pair,
        "worst_pair": worst_pair,
    }


def compute_backtest_metrics(
    *,
    stored_rule: Any,
    proposed_rule: Any,
    test_records: Iterable[TestingRecordLog],
    label_lookup: dict[int, str],
) -> dict[str, Any]:
    total_records = 0
    labeled_records = 0
    label_counts: Counter[str] = Counter()
    quality_outcomes: set[str] = set()

    stored_metrics = _RuleMetricsAccumulator()
    proposed_metrics = _RuleMetricsAccumulator()

    for record in test_records:
        total_records += 1

        label_name: str | None = None
        if record.el_id is not None:
            label_name = label_lookup.get(int(record.el_id))
            if label_name is not None:
                labeled_records += 1
                label_counts[label_name] += 1

        stored_outcome = stored_rule(record.event)
        proposed_outcome = proposed_rule(record.event)

        stored_outcome_name = str(stored_outcome) if stored_outcome is not None else None
        proposed_outcome_name = str(proposed_outcome) if proposed_outcome is not None else None

        stored_metrics.record(stored_outcome_name, label_name)
        proposed_metrics.record(proposed_outcome_name, label_name)

        if label_name is None:
            continue
        if stored_outcome_name is not None:
            quality_outcomes.add(stored_outcome_name)
        if proposed_outcome_name is not None:
            quality_outcomes.add(proposed_outcome_name)

    ordered_outcomes = sorted(quality_outcomes)
    ordered_labels = sorted(label_counts)

    stored_quality_metrics, stored_quality_summary = _build_quality_metrics(
        outcomes=ordered_outcomes,
        labels=ordered_labels,
        accumulator=stored_metrics,
        label_counts=label_counts,
    )
    proposed_quality_metrics, proposed_quality_summary = _build_quality_metrics(
        outcomes=ordered_outcomes,
        labels=ordered_labels,
        accumulator=proposed_metrics,
        label_counts=label_counts,
    )

    return {
        "stored_result": _sorted_counts(stored_metrics.outcome_counts),
        "proposed_result": _sorted_counts(proposed_metrics.outcome_counts),
        "stored_result_rate": _count_rates(stored_metrics.outcome_counts, total_records),
        "proposed_result_rate": _count_rates(proposed_metrics.outcome_counts, total_records),
        "total_records": total_records,
        "labeled_records": labeled_records,
        "label_counts": _sorted_counts(label_counts),
        "stored_quality_metrics": stored_quality_metrics,
        "proposed_quality_metrics": proposed_quality_metrics,
        "stored_quality_summary": stored_quality_summary,
        "proposed_quality_summary": proposed_quality_summary,
    }
