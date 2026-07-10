import pytest

from ezrules.backend.quality_metrics import compute_quality_metric_values


def test_quality_metrics_match_four_event_confusion_matrix():
    metric = compute_quality_metric_values(
        true_positive=1,
        predicted_positives=2,
        actual_positives=2,
    )

    assert metric == {
        "true_positive": 1,
        "false_positive": 1,
        "false_negative": 1,
        "predicted_positives": 2,
        "actual_positives": 2,
        "precision": 0.5,
        "recall": 0.5,
        "f1": 0.5,
    }


@pytest.mark.parametrize(
    ("predicted_positives", "actual_positives", "expected_precision", "expected_recall", "expected_f1"),
    [
        (0, 2, None, 0.0, None),
        (2, 0, 0.0, None, None),
        (0, 0, None, None, None),
        (2, 2, 0.0, 0.0, 0.0),
    ],
)
def test_quality_metrics_define_zero_denominator_semantics(
    predicted_positives,
    actual_positives,
    expected_precision,
    expected_recall,
    expected_f1,
):
    metric = compute_quality_metric_values(
        true_positive=0,
        predicted_positives=predicted_positives,
        actual_positives=actual_positives,
    )

    assert metric["precision"] == expected_precision
    assert metric["recall"] == expected_recall
    assert metric["f1"] == expected_f1


@pytest.mark.parametrize(
    ("true_positive", "predicted_positives", "actual_positives"),
    [
        (-1, 0, 0),
        (0, -1, 0),
        (0, 0, -1),
        (2, 1, 2),
        (2, 2, 1),
    ],
)
def test_quality_metrics_reject_impossible_counts(
    true_positive,
    predicted_positives,
    actual_positives,
):
    with pytest.raises(ValueError):
        compute_quality_metric_values(
            true_positive=true_positive,
            predicted_positives=predicted_positives,
            actual_positives=actual_positives,
        )
