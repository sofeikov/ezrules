from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

ALLOWED_WINDOW_SECONDS = {
    600: "10m",
    3600: "1h",
    86400: "24h",
    604800: "7d",
    2592000: "30d",
    7776000: "90d",
}

MAX_ONLINE_WINDOW_SECONDS = 7776000


class FeatureAggregation(str, Enum):
    COUNT = "count"
    COUNT_DISTINCT = "count_distinct"
    SUM = "sum"
    AVG = "avg"
    MIN = "min"
    MAX = "max"
    STDDEV = "stddev"
    DAYS_SINCE_FIRST_SEEN = "days_since_first_seen"


class FeatureStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    DEPRECATED = "deprecated"


class FeatureFilter(BaseModel):
    field: str = Field(..., min_length=1)
    operator: Literal["eq", "in"] = "eq"
    value: Any


class FeatureDefinitionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    entity: str = Field(..., pattern=r"^[A-Za-z_][A-Za-z0-9_]*$", max_length=64)
    feature_name: str = Field(..., pattern=r"^[A-Za-z_][A-Za-z0-9_]*$", max_length=128)
    entity_key: str = Field(..., min_length=1)
    aggregation_type: FeatureAggregation
    source_field: str | None = None
    window_seconds: int = Field(..., gt=0, le=MAX_ONLINE_WINDOW_SECONDS)
    filters: list[FeatureFilter] = Field(default_factory=list, max_length=5)
    inclusion_policy: Literal["previous_events"] = "previous_events"
    null_handling: Literal["exclude", "zero"] = "exclude"

    @field_validator("window_seconds")
    @classmethod
    def validate_preset_window(cls, value: int) -> int:
        if value not in ALLOWED_WINDOW_SECONDS:
            allowed = ", ".join(ALLOWED_WINDOW_SECONDS.values())
            raise ValueError(f"window_seconds must use one of the preset windows: {allowed}")
        return value

    @field_validator("source_field")
    @classmethod
    def validate_source_field(cls, value: str | None, info):
        aggregation = info.data.get("aggregation_type")
        needs_source = {
            FeatureAggregation.COUNT_DISTINCT,
            FeatureAggregation.SUM,
            FeatureAggregation.AVG,
            FeatureAggregation.MIN,
            FeatureAggregation.MAX,
            FeatureAggregation.STDDEV,
        }
        if aggregation in needs_source and not value:
            raise ValueError(f"source_field is required for {aggregation}")
        return value


class FeatureDefinitionUpdate(FeatureDefinitionCreate):
    pass


class FeatureDefinitionResponse(BaseModel):
    fd_id: int
    name: str
    description: str | None = None
    entity: str
    feature_name: str
    available_as: str
    entity_key: str
    aggregation_type: str
    source_field: str | None = None
    window_seconds: int
    window_label: str
    filters: list[FeatureFilter]
    inclusion_policy: str
    null_handling: str
    status: FeatureStatus
    version: int
    dependency_count: int = 0
    created_at: datetime
    updated_at: datetime


class FeatureDefinitionListResponse(BaseModel):
    features: list[FeatureDefinitionResponse]


class FeatureMutationResponse(BaseModel):
    success: bool
    message: str
    feature: FeatureDefinitionResponse | None = None


class FeaturePreviewRequest(BaseModel):
    event_data: dict[str, Any]
    as_of: datetime


class FeaturePreviewResponse(BaseModel):
    value: Any
    matched_event_count: int
    as_of: datetime
    window_start: datetime


class FeatureDependencyResponse(BaseModel):
    r_id: int
    rid: str
    description: str
    status: str


class FeatureDependencyListResponse(BaseModel):
    dependencies: list[FeatureDependencyResponse]
