"""
Pydantic schemas for analytics-related API endpoints.

These schemas define the request/response format for the Analytics API.
Analytics endpoints provide time-series data for dashboards and charts.
"""

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
