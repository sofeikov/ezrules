from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ALLOWED_WINDOW_SECONDS = {
    600: "10m",
    3600: "1h",
    86400: "24h",
    604800: "7d",
    2592000: "30d",
    7776000: "90d",
    15552000: "180d",
}

MAX_ONLINE_WINDOW_SECONDS = 15552000


class FeatureKind(str, Enum):
    AGGREGATE = "aggregate"
    GRAPH = "graph"


class FeatureAggregation(str, Enum):
    COUNT = "count"
    COUNT_DISTINCT = "count_distinct"
    SUM = "sum"
    AVG = "avg"
    MIN = "min"
    MAX = "max"
    STDDEV = "stddev"
    DAYS_SINCE_FIRST_SEEN = "days_since_first_seen"
    GRAPH_DISTINCT_COUNT = "graph_distinct_count"


class FeatureStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    DEPRECATED = "deprecated"


class FeatureFilter(BaseModel):
    field: str = Field(..., min_length=1)
    operator: Literal["eq", "in"] = "eq"
    value: Any


class GraphFeatureConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_entity: str = Field(..., pattern=r"^[A-Za-z_][A-Za-z0-9_]*$", max_length=64)
    allowed_entity_types: list[str] = Field(..., min_length=1, max_length=12)
    max_depth: int = Field(default=4, ge=1, le=6)
    max_expanded_nodes: int = Field(default=10_000, ge=1, le=50_000)

    @field_validator("allowed_entity_types")
    @classmethod
    def validate_allowed_entity_types(cls, value: list[str]) -> list[str]:
        normalized = list(dict.fromkeys(item.strip() for item in value if item.strip()))
        if not normalized:
            raise ValueError("allowed_entity_types must include at least one entity type")
        for item in normalized:
            if not item.replace("_", "a").isalnum() or item[0].isdigit():
                raise ValueError("allowed_entity_types must contain identifier-like values")
        return normalized

    @model_validator(mode="after")
    def validate_target_is_traversable(self):
        if self.target_entity not in self.allowed_entity_types:
            raise ValueError("target_entity must be included in allowed_entity_types")
        return self


class FeatureDefinitionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    entity: str = Field(..., pattern=r"^[A-Za-z_][A-Za-z0-9_]*$", max_length=64)
    feature_name: str = Field(..., pattern=r"^[A-Za-z_][A-Za-z0-9_]*$", max_length=128)
    feature_kind: FeatureKind = FeatureKind.AGGREGATE
    entity_key: str = Field(..., min_length=1)
    aggregation_type: FeatureAggregation
    source_field: str | None = None
    window_seconds: int = Field(..., gt=0, le=MAX_ONLINE_WINDOW_SECONDS)
    filters: list[FeatureFilter] = Field(default_factory=list, max_length=5)
    inclusion_policy: Literal["previous_events"] = "previous_events"
    null_handling: Literal["exclude", "zero"] = "exclude"
    graph_config: GraphFeatureConfig | None = None

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
        feature_kind = info.data.get("feature_kind")
        if feature_kind == FeatureKind.GRAPH:
            return value
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

    @model_validator(mode="after")
    def validate_feature_kind_shape(self):
        if self.feature_kind == FeatureKind.GRAPH:
            if self.aggregation_type != FeatureAggregation.GRAPH_DISTINCT_COUNT:
                raise ValueError("graph features currently support aggregation_type=graph_distinct_count")
            if self.graph_config is None:
                raise ValueError("graph_config is required for graph features")
            if self.source_field is not None:
                raise ValueError("source_field is not used by graph features")
            if self.entity not in self.graph_config.allowed_entity_types:
                raise ValueError("entity must be included in graph_config.allowed_entity_types")
        elif self.graph_config is not None:
            raise ValueError("graph_config is only valid for graph features")
        elif self.aggregation_type == FeatureAggregation.GRAPH_DISTINCT_COUNT:
            raise ValueError("graph_distinct_count requires feature_kind=graph")
        return self


class FeatureDefinitionUpdate(FeatureDefinitionCreate):
    pass


class FeatureDefinitionResponse(BaseModel):
    fd_id: int
    name: str
    description: str | None = None
    entity: str
    feature_name: str
    available_as: str
    feature_kind: FeatureKind
    entity_key: str
    aggregation_type: str
    source_field: str | None = None
    window_seconds: int
    window_label: str
    filters: list[FeatureFilter]
    inclusion_policy: str
    null_handling: str
    graph_config: GraphFeatureConfig | None = None
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
