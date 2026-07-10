"""Shared binary quality-metric calculations."""

from __future__ import annotations

from typing import TypedDict


class QualityMetricValues(TypedDict):
    true_positive: int
    false_positive: int
    false_negative: int
    predicted_positives: int
    actual_positives: int
    precision: float | None
    recall: float | None
    f1: float | None


def compute_quality_metric_values(
    *,
    true_positive: int,
    predicted_positives: int,
    actual_positives: int,
) -> QualityMetricValues:
    """Return confusion counts and precision/recall/F1 for one binary pair."""
    if min(true_positive, predicted_positives, actual_positives) < 0:
        raise ValueError("Quality metric counts must be non-negative")
    if true_positive > predicted_positives:
        raise ValueError("True positives cannot exceed predicted positives")
    if true_positive > actual_positives:
        raise ValueError("True positives cannot exceed actual positives")

    false_positive = predicted_positives - true_positive
    false_negative = actual_positives - true_positive
    precision = true_positive / predicted_positives if predicted_positives > 0 else None
    recall = true_positive / actual_positives if actual_positives > 0 else None

    f1 = None
    if precision is not None and recall is not None:
        denominator = precision + recall
        f1 = 0.0 if denominator == 0 else 2 * precision * recall / denominator

    return {
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "predicted_positives": predicted_positives,
        "actual_positives": actual_positives,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }
