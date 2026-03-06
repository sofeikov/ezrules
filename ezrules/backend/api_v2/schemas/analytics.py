"""
Pydantic schemas for analytics-related API endpoints.

These schemas define the request/response format for the Analytics API.
Analytics endpoints provide time-series data for dashboards and charts.
"""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

# =============================================================================
# ENUMS
# =============================================================================


class AggregationPeriod(str, Enum):
    """Valid aggregation periods for analytics queries."""

    ONE_HOUR = "1h"
    SIX_HOURS = "6h"
    TWELVE_HOURS = "12h"
    TWENTY_FOUR_HOURS = "24h"
    THIRTY_DAYS = "30d"


# =============================================================================
# RESPONSE SCHEMAS
# =============================================================================


class TimeSeriesResponse(BaseModel):
    """Response for simple time-series data (single line chart)."""

    labels: list[str] = Field(..., description="Time labels for x-axis")
    data: list[int] = Field(..., description="Values for y-axis")
    aggregation: str = Field(..., description="Aggregation period used")


class ChartDataset(BaseModel):
    """A single dataset for Chart.js multi-line charts."""

    label: str = Field(..., description="Dataset label (e.g., outcome name)")
    data: list[int] = Field(..., description="Values for this dataset")
    borderColor: str = Field(..., description="Line color")
    backgroundColor: str = Field(..., description="Fill color")
    tension: float = Field(default=0.3, description="Line tension")
    fill: bool = Field(default=True, description="Whether to fill under line")


class MultiSeriesResponse(BaseModel):
    """Response for multi-series time-series data (multiple line charts)."""

    labels: list[str] = Field(..., description="Time labels for x-axis")
    datasets: list[ChartDataset] = Field(..., description="Multiple datasets")
    aggregation: str = Field(..., description="Aggregation period used")


class PieChartData(BaseModel):
    """Pie chart data for label distribution."""

    labels: list[str] = Field(..., description="Pie slice labels")
    data: list[int] = Field(..., description="Pie slice values")
    backgroundColor: list[str] = Field(..., description="Slice colors")


class LabelsSummaryResponse(BaseModel):
    """Response for labels summary statistics."""

    total_labeled: int = Field(..., description="Total number of labeled events")
    pie_chart: PieChartData = Field(..., description="Label distribution pie chart data")


class RuleQualityPairMetric(BaseModel):
    """Precision/recall metrics for a single (rule outcome -> label) pair."""

    r_id: int = Field(..., description="Rule database ID")
    rid: str = Field(..., description="Rule external ID")
    description: str = Field(..., description="Rule description")
    outcome: str = Field(..., description="Rule outcome being treated as a prediction")
    label: str = Field(..., description="Ground-truth label being compared against")
    true_positive: int = Field(..., description="Events where outcome and label both matched")
    false_positive: int = Field(..., description="Events with outcome but different label")
    false_negative: int = Field(..., description="Events with label but different outcome")
    predicted_positives: int = Field(..., description="Total events predicted by this outcome")
    actual_positives: int = Field(..., description="Total events carrying this label")
    precision: float | None = Field(..., description="True positive / predicted positives")
    recall: float | None = Field(..., description="True positive / actual positives")
    f1: float | None = Field(..., description="Harmonic mean of precision and recall")


class RuleQualitySummary(BaseModel):
    """Aggregate quality summary for a single rule."""

    r_id: int = Field(..., description="Rule database ID")
    rid: str = Field(..., description="Rule external ID")
    description: str = Field(..., description="Rule description")
    labeled_events: int = Field(..., description="Number of labeled events evaluated by the rule")
    pair_count: int = Field(..., description="Number of outcome-label pairs used in averages")
    average_precision: float | None = Field(..., description="Average precision across included pairs")
    average_recall: float | None = Field(..., description="Average recall across included pairs")
    average_f1: float | None = Field(..., description="Average F1 across included pairs")
    best_pair: str | None = Field(..., description="Best (outcome -> label) pair by F1")
    worst_pair: str | None = Field(..., description="Worst (outcome -> label) pair by F1")


class RuleQualityResponse(BaseModel):
    """Rule quality analytics built from labeled events."""

    total_labeled_events: int = Field(..., description="Count of labeled events in the dataset")
    min_support: int = Field(..., description="Minimum support filter applied to pair metrics")
    lookback_days: int = Field(..., description="Lookback window (days) applied to labeled events")
    freeze_at: datetime = Field(..., description="Snapshot timestamp used for this report")
    pair_metrics: list[RuleQualityPairMetric] = Field(..., description="Pair-level quality metrics")
    best_rules: list[RuleQualitySummary] = Field(..., description="Top rules by average F1")
    worst_rules: list[RuleQualitySummary] = Field(..., description="Lowest rules by average F1")


class RuleQualityReportRequest(BaseModel):
    """Request payload for rule-quality report generation."""

    min_support: int = Field(default=1, ge=1, description="Minimum support threshold")
    lookback_days: int | None = Field(
        default=None,
        ge=1,
        description="Lookback window in days (defaults to runtime setting when omitted)",
    )
    force_refresh: bool = Field(
        default=False,
        description="When true, always enqueue a fresh report instead of reusing cache",
    )


class RuleQualityReportTaskResponse(BaseModel):
    """Status payload for async rule-quality reports."""

    report_id: int = Field(..., description="Database ID of the report request")
    task_id: str | None = Field(..., description="Celery task ID when dispatched")
    status: str = Field(..., description="Report status: PENDING, RUNNING, SUCCESS, FAILURE")
    min_support: int = Field(..., description="Minimum support threshold")
    lookback_days: int = Field(..., description="Lookback window in days")
    freeze_at: datetime = Field(..., description="Snapshot timestamp for report consistency")
    created_at: datetime = Field(..., description="Report creation timestamp")
    started_at: datetime | None = Field(default=None, description="When computation started")
    completed_at: datetime | None = Field(default=None, description="When computation completed")
    cached: bool = Field(default=False, description="True when an existing report is reused")
    error: str | None = Field(default=None, description="Failure message when status is FAILURE")
    result: RuleQualityResponse | None = Field(default=None, description="Computed report payload on SUCCESS")


class AnalyticsErrorResponse(BaseModel):
    """Error response for analytics endpoints."""

    error: str


# =============================================================================
# CHART COLORS
# =============================================================================

# Default colors for Chart.js charts
CHART_COLORS = [
    {"border": "rgb(255, 99, 132)", "background": "rgba(255, 99, 132, 0.1)"},
    {"border": "rgb(54, 162, 235)", "background": "rgba(54, 162, 235, 0.1)"},
    {"border": "rgb(255, 206, 86)", "background": "rgba(255, 206, 86, 0.1)"},
    {"border": "rgb(75, 192, 192)", "background": "rgba(75, 192, 192, 0.1)"},
    {"border": "rgb(153, 102, 255)", "background": "rgba(153, 102, 255, 0.1)"},
    {"border": "rgb(255, 159, 64)", "background": "rgba(255, 159, 64, 0.1)"},
    {"border": "rgb(201, 203, 207)", "background": "rgba(201, 203, 207, 0.1)"},
]

PIE_COLORS = [
    "rgb(255, 99, 132)",
    "rgb(54, 162, 235)",
    "rgb(255, 206, 86)",
    "rgb(75, 192, 192)",
    "rgb(153, 102, 255)",
    "rgb(255, 159, 64)",
    "rgb(201, 203, 207)",
]
