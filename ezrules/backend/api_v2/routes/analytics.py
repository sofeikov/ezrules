"""
FastAPI routes for analytics and dashboard data.

These endpoints provide time-series data for dashboards and charts.
All endpoints require authentication and appropriate permissions.
"""

import datetime
from typing import Any

import sqlalchemy
from fastapi import APIRouter, Depends, HTTPException, Query, status

from ezrules.backend.analytics import AGGREGATION_CONFIG, get_bucket_expression
from ezrules.backend.api_v2.auth.dependencies import (
    get_current_active_user,
    get_db,
    require_permission,
)
from ezrules.backend.api_v2.schemas.analytics import (
    CHART_COLORS,
    PIE_COLORS,
    ChartDataset,
    LabelsSummaryResponse,
    MultiSeriesResponse,
    PieChartData,
    TimeSeriesResponse,
)
from ezrules.core.permissions_constants import PermissionAction
from ezrules.models.backend_core import Label, TestingRecordLog, TestingResultsLog, User

router = APIRouter(prefix="/api/v2/analytics", tags=["Analytics"])


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def validate_aggregation(aggregation: str) -> dict[str, Any]:
    """Validate and return aggregation config."""
    if aggregation not in AGGREGATION_CONFIG:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid aggregation. Valid options: {list(AGGREGATION_CONFIG.keys())}",
        )
    return AGGREGATION_CONFIG[aggregation]


def format_bucket_label(bucket: Any, config: dict[str, Any]) -> str:
    """Format a time bucket into a label string."""
    if config["use_date_trunc"]:
        return bucket.strftime(config["label_format"])
    else:
        dt = datetime.datetime.fromtimestamp(bucket)
        return dt.strftime(config["label_format"])


# =============================================================================
# TRANSACTION VOLUME
# =============================================================================


@router.get("/transaction-volume", response_model=TimeSeriesResponse)
def get_transaction_volume(
    aggregation: str = Query(default="1h", description="Aggregation period"),
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.VIEW_RULES)),
    db: Any = Depends(get_db),
) -> TimeSeriesResponse:
    """
    Get transaction volume over time.

    Returns time-series data showing the number of transactions in each time bucket.
    """
    config = validate_aggregation(aggregation)
    start_time = datetime.datetime.now() - config["delta"]

    bucket_expr = get_bucket_expression(config, TestingRecordLog.created_at)

    transactions = (
        db.query(bucket_expr.label("bucket"), sqlalchemy.func.count(TestingRecordLog.tl_id).label("count"))
        .filter(TestingRecordLog.created_at >= start_time)
        .group_by("bucket")
        .order_by("bucket")
        .all()
    )

    labels = []
    data = []

    for bucket, count in transactions:
        labels.append(format_bucket_label(bucket, config))
        data.append(count)

    return TimeSeriesResponse(labels=labels, data=data, aggregation=aggregation)


# =============================================================================
# OUTCOMES DISTRIBUTION
# =============================================================================


@router.get("/outcomes-distribution", response_model=MultiSeriesResponse)
def get_outcomes_distribution(
    aggregation: str = Query(default="1h", description="Aggregation period"),
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.VIEW_OUTCOMES)),
    db: Any = Depends(get_db),
) -> MultiSeriesResponse:
    """
    Get distribution of rule outcomes over time.

    Returns multi-series time-series data showing count of each outcome type.
    """
    config = validate_aggregation(aggregation)
    start_time = datetime.datetime.now() - config["delta"]

    bucket_expr = get_bucket_expression(config, TestingRecordLog.created_at)

    outcomes = (
        db.query(
            bucket_expr.label("bucket"),
            TestingResultsLog.rule_result,
            sqlalchemy.func.count(TestingResultsLog.rule_result).label("count"),
        )
        .join(TestingRecordLog, TestingRecordLog.tl_id == TestingResultsLog.tl_id)
        .filter(TestingRecordLog.created_at >= start_time)
        .group_by("bucket", TestingResultsLog.rule_result)
        .order_by("bucket")
        .all()
    )

    # Get unique outcome labels
    outcome_labels = sorted({outcome for _bucket, outcome, _count in outcomes})

    # Organize data by time bucket
    time_buckets: dict[Any, dict[str, int]] = {}
    for bucket, outcome, count in outcomes:
        if bucket not in time_buckets:
            time_buckets[bucket] = {}
        time_buckets[bucket][outcome] = count

    # Format data for Chart.js
    labels = []
    datasets_data: dict[str, list[int]] = {outcome: [] for outcome in outcome_labels}

    sorted_buckets = sorted(time_buckets.keys())
    for bucket in sorted_buckets:
        labels.append(format_bucket_label(bucket, config))

        for outcome in outcome_labels:
            datasets_data[outcome].append(time_buckets[bucket].get(outcome, 0))

    # Build Chart.js datasets
    datasets = []
    for idx, outcome in enumerate(outcome_labels):
        color = CHART_COLORS[idx % len(CHART_COLORS)]
        datasets.append(
            ChartDataset(
                label=outcome,
                data=datasets_data[outcome],
                borderColor=color["border"],
                backgroundColor=color["background"],
                tension=0.3,
                fill=True,
            )
        )

    return MultiSeriesResponse(labels=labels, datasets=datasets, aggregation=aggregation)


# =============================================================================
# LABELS DISTRIBUTION
# =============================================================================


@router.get("/labels-distribution", response_model=MultiSeriesResponse)
def get_labels_distribution(
    aggregation: str = Query(default="1h", description="Aggregation period"),
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.VIEW_LABELS)),
    db: Any = Depends(get_db),
) -> MultiSeriesResponse:
    """
    Get distribution of labels over time.

    Returns multi-series time-series data showing count of each label type.
    """
    config = validate_aggregation(aggregation)
    start_time = datetime.datetime.now() - config["delta"]

    bucket_expr = get_bucket_expression(config, TestingRecordLog.created_at)

    labels_data = (
        db.query(
            bucket_expr.label("bucket"),
            Label.label,
            sqlalchemy.func.count(Label.label).label("count"),
        )
        .join(TestingRecordLog, TestingRecordLog.el_id == Label.el_id)
        .filter(TestingRecordLog.created_at >= start_time)
        .filter(TestingRecordLog.el_id.isnot(None))
        .group_by("bucket", Label.label)
        .order_by("bucket")
        .all()
    )

    # Get unique label names
    label_names = sorted({label_name for _bucket, label_name, _count in labels_data})

    # Organize data by time bucket
    time_buckets: dict[Any, dict[str, int]] = {}
    for bucket, label_name, count in labels_data:
        if bucket not in time_buckets:
            time_buckets[bucket] = {}
        time_buckets[bucket][label_name] = count

    # Format data for Chart.js
    labels = []
    datasets_data: dict[str, list[int]] = {label_name: [] for label_name in label_names}

    sorted_buckets = sorted(time_buckets.keys())
    for bucket in sorted_buckets:
        labels.append(format_bucket_label(bucket, config))

        for label_name in label_names:
            datasets_data[label_name].append(time_buckets[bucket].get(label_name, 0))

    # Build Chart.js datasets
    datasets = []
    for idx, label_name in enumerate(label_names):
        color = CHART_COLORS[idx % len(CHART_COLORS)]
        datasets.append(
            ChartDataset(
                label=label_name,
                data=datasets_data[label_name],
                borderColor=color["border"],
                backgroundColor=color["background"],
                tension=0.3,
                fill=True,
            )
        )

    return MultiSeriesResponse(labels=labels, datasets=datasets, aggregation=aggregation)


# =============================================================================
# LABELED TRANSACTION VOLUME
# =============================================================================


@router.get("/labeled-transaction-volume", response_model=TimeSeriesResponse)
def get_labeled_transaction_volume(
    aggregation: str = Query(default="1h", description="Aggregation period"),
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.VIEW_LABELS)),
    db: Any = Depends(get_db),
) -> TimeSeriesResponse:
    """
    Get labeled transaction volume over time.

    Returns time-series data showing the number of labeled transactions in each time bucket.
    """
    config = validate_aggregation(aggregation)
    start_time = datetime.datetime.now() - config["delta"]

    bucket_expr = get_bucket_expression(config, TestingRecordLog.created_at)

    transactions = (
        db.query(bucket_expr.label("bucket"), sqlalchemy.func.count(TestingRecordLog.tl_id).label("count"))
        .filter(TestingRecordLog.created_at >= start_time)
        .filter(TestingRecordLog.el_id.isnot(None))
        .group_by("bucket")
        .order_by("bucket")
        .all()
    )

    labels = []
    data = []

    for bucket, count in transactions:
        labels.append(format_bucket_label(bucket, config))
        data.append(count)

    return TimeSeriesResponse(labels=labels, data=data, aggregation=aggregation)


# =============================================================================
# LABELS SUMMARY
# =============================================================================


@router.get("/labels-summary", response_model=LabelsSummaryResponse)
def get_labels_summary(
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.VIEW_LABELS)),
    db: Any = Depends(get_db),
) -> LabelsSummaryResponse:
    """
    Get summary statistics for labels.

    Returns total labeled events count and pie chart data for label distribution.
    """
    # Total labeled events
    total_labeled = (
        db.query(sqlalchemy.func.count(TestingRecordLog.tl_id)).filter(TestingRecordLog.el_id.isnot(None)).scalar()
    )

    # Label distribution (pie chart data)
    label_counts = (
        db.query(Label.label, sqlalchemy.func.count(TestingRecordLog.tl_id).label("count"))
        .join(TestingRecordLog, TestingRecordLog.el_id == Label.el_id)
        .filter(TestingRecordLog.el_id.isnot(None))
        .group_by(Label.label)
        .order_by(sqlalchemy.desc("count"))
        .all()
    )

    pie_labels = []
    pie_data = []

    for label_name, count in label_counts:
        pie_labels.append(label_name)
        pie_data.append(count)

    return LabelsSummaryResponse(
        total_labeled=total_labeled or 0,
        pie_chart=PieChartData(
            labels=pie_labels,
            data=pie_data,
            backgroundColor=PIE_COLORS[: len(pie_labels)],
        ),
    )
