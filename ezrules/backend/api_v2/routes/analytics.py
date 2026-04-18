"""
FastAPI routes for analytics and dashboard data.

These endpoints provide time-series data for dashboards and charts.
All endpoints require authentication and appropriate permissions.
"""

import datetime
from typing import Any, cast

import sqlalchemy
from fastapi import APIRouter, Depends, HTTPException, Query, status

from ezrules.backend.analytics import AGGREGATION_CONFIG, get_bucket_expression
from ezrules.backend.api_v2.auth.dependencies import (
    get_current_active_user,
    get_current_org_id,
    get_db,
    require_permission,
)
from ezrules.backend.api_v2.schemas.analytics import (
    CHART_COLORS,
    PIE_COLORS,
    AggregationPeriod,
    ChartDataset,
    LabelsSummaryResponse,
    MultiSeriesResponse,
    PieChartData,
    RuleActivityResponse,
    RuleFireActivityItem,
    RuleQualityReportRequest,
    RuleQualityReportTaskResponse,
    RuleQualityResponse,
    TimeSeriesResponse,
)
from ezrules.backend.rule_quality import (
    compute_rule_quality_metrics,
    compute_rule_quality_pairs_hash,
    get_active_rule_quality_pairs,
    get_rule_quality_snapshot_max_tl_id,
)
from ezrules.backend.runtime_settings import get_rule_quality_lookback_days
from ezrules.backend.tasks import generate_rule_quality_report
from ezrules.core.permissions_constants import PermissionAction
from ezrules.models.backend_core import Label, RuleQualityReport, RuleStatus, TestingRecordLog, TestingResultsLog, User
from ezrules.models.backend_core import Rule as RuleModel
from ezrules.settings import app_settings

router = APIRouter(prefix="/api/v2/analytics", tags=["Analytics"])


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def validate_aggregation(aggregation: str | AggregationPeriod) -> tuple[AggregationPeriod, dict[str, Any]]:
    """Validate and normalize an aggregation value."""
    try:
        period = aggregation if isinstance(aggregation, AggregationPeriod) else AggregationPeriod(aggregation)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid aggregation. Valid options: {list(AGGREGATION_CONFIG.keys())}",
        ) from exc
    return period, AGGREGATION_CONFIG[period.value]


def get_current_time_bounds(delta: datetime.timedelta | None = None) -> tuple[datetime.datetime, datetime.datetime]:
    """Return a naive datetime window that tolerates local-vs-UTC stored timestamps."""
    local_now = datetime.datetime.now()
    utc_now = datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
    window_start = min(local_now, utc_now)
    window_end = max(local_now, utc_now)
    if delta is not None:
        window_start -= delta
    return window_start, window_end


def format_bucket_label(bucket: Any, config: dict[str, Any]) -> str:
    """Format a time bucket into a label string."""
    if config["use_date_trunc"]:
        return bucket.strftime(config["label_format"])
    else:
        dt = datetime.datetime.fromtimestamp(bucket)
        return dt.strftime(config["label_format"])


def build_rule_activity_items(rows: list[Any]) -> list[RuleFireActivityItem]:
    """Normalize SQL rows into rule-activity response items."""
    return [
        RuleFireActivityItem(
            r_id=int(row.r_id),
            rid=str(row.rid),
            description=str(row.description),
            fire_count=int(row.fire_count),
        )
        for row in rows
    ]


# =============================================================================
# TRANSACTION VOLUME
# =============================================================================


@router.get("/transaction-volume", response_model=TimeSeriesResponse)
def get_transaction_volume(
    aggregation: str = Query(default=AggregationPeriod.ONE_HOUR.value, description="Aggregation period"),
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.VIEW_RULES)),
    current_org_id: int = Depends(get_current_org_id),
    db: Any = Depends(get_db),
) -> TimeSeriesResponse:
    """
    Get transaction volume over time.

    Returns time-series data showing the number of transactions in each time bucket.
    """
    aggregation_period, config = validate_aggregation(aggregation)
    start_time, end_time = get_current_time_bounds(config["delta"])

    bucket_expr = get_bucket_expression(config, TestingRecordLog.created_at)

    transactions = (
        db.query(bucket_expr.label("bucket"), sqlalchemy.func.count(TestingRecordLog.tl_id).label("count"))
        .filter(TestingRecordLog.created_at >= start_time)
        .filter(TestingRecordLog.created_at <= end_time)
        .filter(TestingRecordLog.o_id == current_org_id)
        .group_by("bucket")
        .order_by("bucket")
        .all()
    )

    labels = []
    data = []

    for bucket, count in transactions:
        labels.append(format_bucket_label(bucket, config))
        data.append(count)

    return TimeSeriesResponse(labels=labels, data=data, aggregation=aggregation_period)


# =============================================================================
# OUTCOMES DISTRIBUTION
# =============================================================================


@router.get("/outcomes-distribution", response_model=MultiSeriesResponse)
def get_outcomes_distribution(
    aggregation: str = Query(default=AggregationPeriod.ONE_HOUR.value, description="Aggregation period"),
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.VIEW_OUTCOMES)),
    current_org_id: int = Depends(get_current_org_id),
    db: Any = Depends(get_db),
) -> MultiSeriesResponse:
    """
    Get distribution of rule outcomes over time.

    Returns multi-series time-series data showing count of each outcome type.
    """
    aggregation_period, config = validate_aggregation(aggregation)
    start_time, end_time = get_current_time_bounds(config["delta"])

    bucket_expr = get_bucket_expression(config, TestingRecordLog.created_at)

    outcomes = (
        db.query(
            bucket_expr.label("bucket"),
            TestingResultsLog.rule_result,
            sqlalchemy.func.count(TestingResultsLog.rule_result).label("count"),
        )
        .join(TestingRecordLog, TestingRecordLog.tl_id == TestingResultsLog.tl_id)
        .filter(TestingRecordLog.created_at >= start_time)
        .filter(TestingRecordLog.created_at <= end_time)
        .filter(TestingRecordLog.o_id == current_org_id)
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

    return MultiSeriesResponse(labels=labels, datasets=datasets, aggregation=aggregation_period)


# =============================================================================
# RULE ACTIVITY
# =============================================================================


@router.get("/rule-activity", response_model=RuleActivityResponse)
def get_rule_activity(
    aggregation: str = Query(default=AggregationPeriod.SIX_HOURS.value, description="Aggregation period"),
    limit: int = Query(default=5, ge=1, le=50, description="Maximum rules returned per ranking"),
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.VIEW_RULES)),
    current_org_id: int = Depends(get_current_org_id),
    db: Any = Depends(get_db),
) -> RuleActivityResponse:
    """
    Return most/least firing active rules for the selected time window.

    Fire counts are derived from stored non-null rule outcomes in testing_results_log.
    """
    aggregation_period, config = validate_aggregation(aggregation)
    start_time, end_time = get_current_time_bounds(config["delta"])

    fire_counts = (
        db.query(
            TestingResultsLog.r_id.label("r_id"),
            sqlalchemy.func.count(TestingResultsLog.tr_id).label("fire_count"),
        )
        .join(TestingRecordLog, TestingRecordLog.tl_id == TestingResultsLog.tl_id)
        .filter(TestingRecordLog.created_at >= start_time)
        .filter(TestingRecordLog.created_at <= end_time)
        .filter(TestingRecordLog.o_id == current_org_id)
        .filter(TestingResultsLog.rule_result.isnot(None))
        .group_by(TestingResultsLog.r_id)
        .subquery()
    )

    fire_count_expr = sqlalchemy.func.coalesce(fire_counts.c.fire_count, 0)
    base_query = (
        db.query(
            RuleModel.r_id.label("r_id"),
            RuleModel.rid.label("rid"),
            RuleModel.description.label("description"),
            fire_count_expr.label("fire_count"),
        )
        .outerjoin(fire_counts, fire_counts.c.r_id == RuleModel.r_id)
        .filter(RuleModel.o_id == current_org_id)
        .filter(RuleModel.status == RuleStatus.ACTIVE)
    )

    most_firing_rows = base_query.order_by(fire_count_expr.desc(), RuleModel.rid.asc()).limit(limit).all()
    least_firing_rows = base_query.order_by(fire_count_expr.asc(), RuleModel.rid.asc()).limit(limit).all()

    return RuleActivityResponse(
        aggregation=aggregation_period,
        limit=limit,
        most_firing=build_rule_activity_items(most_firing_rows),
        least_firing=build_rule_activity_items(least_firing_rows),
    )


# =============================================================================
# RULE OUTCOMES DISTRIBUTION
# =============================================================================


@router.get("/rules/{rule_id}/outcomes-distribution", response_model=MultiSeriesResponse)
def get_rule_outcomes_distribution(
    rule_id: int,
    aggregation: str = Query(default=AggregationPeriod.SIX_HOURS.value, description="Aggregation period"),
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.VIEW_RULES)),
    current_org_id: int = Depends(get_current_org_id),
    db: Any = Depends(get_db),
) -> MultiSeriesResponse:
    """
    Get outcome hit counts over time for one rule.

    Returns multi-series time-series data showing how often each stored outcome
    fired for the selected rule in the chosen time window.
    """
    aggregation_period, config = validate_aggregation(aggregation)
    start_time, end_time = get_current_time_bounds(config["delta"])

    rule = db.query(RuleModel.r_id).filter(RuleModel.r_id == rule_id).filter(RuleModel.o_id == current_org_id).first()
    if rule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found")

    bucket_expr = get_bucket_expression(config, TestingRecordLog.created_at)

    outcomes = (
        db.query(
            bucket_expr.label("bucket"),
            TestingResultsLog.rule_result,
            sqlalchemy.func.count(TestingResultsLog.tr_id).label("count"),
        )
        .join(TestingRecordLog, TestingRecordLog.tl_id == TestingResultsLog.tl_id)
        .filter(TestingResultsLog.r_id == rule_id)
        .filter(TestingRecordLog.created_at >= start_time)
        .filter(TestingRecordLog.created_at <= end_time)
        .filter(TestingRecordLog.o_id == current_org_id)
        .filter(TestingResultsLog.rule_result.isnot(None))
        .group_by("bucket", TestingResultsLog.rule_result)
        .order_by("bucket")
        .all()
    )

    outcome_labels = sorted({outcome for _bucket, outcome, _count in outcomes})

    time_buckets: dict[Any, dict[str, int]] = {}
    for bucket, outcome, count in outcomes:
        if bucket not in time_buckets:
            time_buckets[bucket] = {}
        time_buckets[bucket][outcome] = count

    labels = []
    datasets_data: dict[str, list[int]] = {outcome: [] for outcome in outcome_labels}

    sorted_buckets = sorted(time_buckets.keys())
    for bucket in sorted_buckets:
        labels.append(format_bucket_label(bucket, config))
        for outcome in outcome_labels:
            datasets_data[outcome].append(time_buckets[bucket].get(outcome, 0))

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

    return MultiSeriesResponse(labels=labels, datasets=datasets, aggregation=aggregation_period)


# =============================================================================
# LABELS DISTRIBUTION
# =============================================================================


@router.get("/labels-distribution", response_model=MultiSeriesResponse)
def get_labels_distribution(
    aggregation: str = Query(default=AggregationPeriod.ONE_HOUR.value, description="Aggregation period"),
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.VIEW_LABELS)),
    current_org_id: int = Depends(get_current_org_id),
    db: Any = Depends(get_db),
) -> MultiSeriesResponse:
    """
    Get distribution of labels over time.

    Returns multi-series time-series data showing count of each label type.
    """
    aggregation_period, config = validate_aggregation(aggregation)
    start_time, end_time = get_current_time_bounds(config["delta"])

    bucket_expr = get_bucket_expression(config, TestingRecordLog.created_at)

    labels_data = (
        db.query(
            bucket_expr.label("bucket"),
            Label.label,
            sqlalchemy.func.count(Label.label).label("count"),
        )
        .join(TestingRecordLog, TestingRecordLog.el_id == Label.el_id)
        .filter(TestingRecordLog.created_at >= start_time)
        .filter(TestingRecordLog.created_at <= end_time)
        .filter(TestingRecordLog.o_id == current_org_id)
        .filter(Label.o_id == current_org_id)
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

    return MultiSeriesResponse(labels=labels, datasets=datasets, aggregation=aggregation_period)


# =============================================================================
# LABELED TRANSACTION VOLUME
# =============================================================================


@router.get("/labeled-transaction-volume", response_model=TimeSeriesResponse)
def get_labeled_transaction_volume(
    aggregation: str = Query(default=AggregationPeriod.ONE_HOUR.value, description="Aggregation period"),
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.VIEW_LABELS)),
    current_org_id: int = Depends(get_current_org_id),
    db: Any = Depends(get_db),
) -> TimeSeriesResponse:
    """
    Get labeled transaction volume over time.

    Returns time-series data showing the number of labeled transactions in each time bucket.
    """
    aggregation_period, config = validate_aggregation(aggregation)
    start_time, end_time = get_current_time_bounds(config["delta"])

    bucket_expr = get_bucket_expression(config, TestingRecordLog.created_at)

    transactions = (
        db.query(bucket_expr.label("bucket"), sqlalchemy.func.count(TestingRecordLog.tl_id).label("count"))
        .filter(TestingRecordLog.created_at >= start_time)
        .filter(TestingRecordLog.created_at <= end_time)
        .filter(TestingRecordLog.o_id == current_org_id)
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

    return TimeSeriesResponse(labels=labels, data=data, aggregation=aggregation_period)


# =============================================================================
# LABELS SUMMARY
# =============================================================================


@router.get("/labels-summary", response_model=LabelsSummaryResponse)
def get_labels_summary(
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.VIEW_LABELS)),
    current_org_id: int = Depends(get_current_org_id),
    db: Any = Depends(get_db),
) -> LabelsSummaryResponse:
    """
    Get summary statistics for labels.

    Returns total labeled events count and pie chart data for label distribution.
    """
    # Total labeled events
    total_labeled = (
        db.query(sqlalchemy.func.count(TestingRecordLog.tl_id))
        .filter(TestingRecordLog.o_id == current_org_id)
        .filter(TestingRecordLog.el_id.isnot(None))
        .scalar()
    )

    # Label distribution (pie chart data)
    label_counts = (
        db.query(Label.label, sqlalchemy.func.count(TestingRecordLog.tl_id).label("count"))
        .join(TestingRecordLog, TestingRecordLog.el_id == Label.el_id)
        .filter(TestingRecordLog.o_id == current_org_id)
        .filter(Label.o_id == current_org_id)
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


# =============================================================================
# RULE QUALITY
# =============================================================================


def _serialize_rule_quality_report(
    report: RuleQualityReport,
    *,
    cached: bool,
) -> RuleQualityReportTaskResponse:
    result_payload = RuleQualityResponse(**report.result) if report.result is not None else None
    report_id = cast(int, report.rqr_id)
    task_id = cast(str | None, report.task_id)
    status_value = cast(str, report.status)
    min_support = cast(int, report.min_support)
    lookback_days = cast(int, report.lookback_days)
    freeze_at = cast(datetime.datetime, report.freeze_at)
    created_at = cast(datetime.datetime, report.created_at)
    started_at = cast(datetime.datetime | None, report.started_at)
    completed_at = cast(datetime.datetime | None, report.completed_at)
    error = cast(str | None, report.error)
    return RuleQualityReportTaskResponse(
        report_id=report_id,
        task_id=task_id,
        status=status_value,
        min_support=min_support,
        lookback_days=lookback_days,
        freeze_at=freeze_at,
        created_at=created_at,
        started_at=started_at,
        completed_at=completed_at,
        cached=cached,
        error=error,
        result=result_payload,
    )


@router.get("/rule-quality", response_model=RuleQualityResponse)
def get_rule_quality(
    min_support: int = Query(default=1, ge=1, description="Minimum support for either predicted or actual positives"),
    lookback_days: int | None = Query(
        default=None,
        ge=1,
        description="Only include labeled events created in the last N days (defaults to runtime setting)",
    ),
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.VIEW_RULES)),
    __: None = Depends(require_permission(PermissionAction.VIEW_LABELS)),
    current_org_id: int = Depends(get_current_org_id),
    db: Any = Depends(get_db),
) -> RuleQualityResponse:
    """
    Get precision/recall metrics for rule outcome to label pairs.

    The endpoint only uses labeled events. It builds a confusion matrix per rule
    where each pair treats one rule outcome as a "predicted positive" signal and
    one ground-truth label as the "actual positive" class.
    """
    applied_lookback_days = (
        lookback_days if lookback_days is not None else get_rule_quality_lookback_days(db, current_org_id)
    )
    _window_start, freeze_at = get_current_time_bounds()
    max_tl_id = get_rule_quality_snapshot_max_tl_id(
        db,
        freeze_at=freeze_at,
        o_id=current_org_id,
    )
    payload = compute_rule_quality_metrics(
        db,
        min_support=min_support,
        lookback_days=applied_lookback_days,
        freeze_at=freeze_at,
        max_tl_id=max_tl_id,
        o_id=current_org_id,
        curated_pairs=get_active_rule_quality_pairs(db, o_id=current_org_id),
    )
    return RuleQualityResponse(**payload)


@router.post("/rule-quality/reports", response_model=RuleQualityReportTaskResponse)
def request_rule_quality_report(
    request_data: RuleQualityReportRequest,
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.VIEW_RULES)),
    __: None = Depends(require_permission(PermissionAction.VIEW_LABELS)),
    current_org_id: int = Depends(get_current_org_id),
    db: Any = Depends(get_db),
) -> RuleQualityReportTaskResponse:
    """Create or reuse a rule-quality report request."""
    applied_lookback_days = (
        request_data.lookback_days
        if request_data.lookback_days is not None
        else get_rule_quality_lookback_days(db, current_org_id)
    )
    active_pairs = get_active_rule_quality_pairs(db, o_id=current_org_id)
    pair_set_hash = compute_rule_quality_pairs_hash(active_pairs)
    _window_start, now = get_current_time_bounds()

    if not request_data.force_refresh:
        cached_report = (
            db.query(RuleQualityReport)
            .filter(RuleQualityReport.o_id == current_org_id)
            .filter(RuleQualityReport.min_support == request_data.min_support)
            .filter(RuleQualityReport.lookback_days == applied_lookback_days)
            .filter(RuleQualityReport.pair_set_hash == pair_set_hash)
            .filter(RuleQualityReport.status.in_(["PENDING", "RUNNING", "SUCCESS"]))
            .order_by(RuleQualityReport.created_at.desc())
            .first()
        )
        if cached_report is not None:
            return _serialize_rule_quality_report(cached_report, cached=True)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No existing rule quality snapshot for the requested filters. Use force_refresh=true to generate one.",
        )

    freeze_at = now
    max_tl_id = get_rule_quality_snapshot_max_tl_id(
        db,
        freeze_at=freeze_at,
        o_id=current_org_id,
    )

    report = RuleQualityReport(
        status="PENDING",
        min_support=request_data.min_support,
        lookback_days=applied_lookback_days,
        freeze_at=freeze_at,
        max_tl_id=max_tl_id,
        pair_set_hash=pair_set_hash,
        pair_set=[{"outcome": outcome, "label": label} for outcome, label in active_pairs],
        requested_by=str(user.email),
        o_id=current_org_id,
    )
    db.add(report)
    db.commit()
    db.refresh(report)

    task = generate_rule_quality_report.delay(report.rqr_id)
    report.task_id = task.id
    db.commit()
    db.refresh(report)

    return _serialize_rule_quality_report(report, cached=False)


@router.get("/rule-quality/reports/{report_id}", response_model=RuleQualityReportTaskResponse)
def get_rule_quality_report(
    report_id: int,
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.VIEW_RULES)),
    __: None = Depends(require_permission(PermissionAction.VIEW_LABELS)),
    current_org_id: int = Depends(get_current_org_id),
    db: Any = Depends(get_db),
) -> RuleQualityReportTaskResponse:
    """Return current status (and result when available) for a rule-quality report."""
    report = (
        db.query(RuleQualityReport)
        .filter(RuleQualityReport.rqr_id == report_id)
        .filter(RuleQualityReport.o_id == current_org_id)
        .first()
    )
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Rule quality report not found",
        )

    if (
        app_settings.RULE_QUALITY_REPORT_SYNC_FALLBACK
        and report.status == "PENDING"
        and report.started_at is None
        and report.result is None
    ):
        generate_rule_quality_report(report.rqr_id)
        db.expire_all()
        refreshed = (
            db.query(RuleQualityReport)
            .filter(RuleQualityReport.rqr_id == report_id)
            .filter(RuleQualityReport.o_id == current_org_id)
            .first()
        )
        if refreshed is not None:
            report = refreshed

    return _serialize_rule_quality_report(report, cached=False)
