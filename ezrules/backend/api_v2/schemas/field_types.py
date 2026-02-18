from datetime import datetime

from pydantic import BaseModel, Field

from ezrules.core.type_casting import FieldType

# =============================================================================
# REQUEST SCHEMAS
# =============================================================================


class FieldTypeConfigCreate(BaseModel):
    field_name: str = Field(..., min_length=1, description="Event field name to configure")
    configured_type: FieldType = Field(..., description="Type to cast this field to")
    datetime_format: str | None = Field(
        default=None,
        description="strptime format string, only used when configured_type is datetime. Defaults to ISO 8601.",
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "field_name": "amount",
                "configured_type": "float",
                "datetime_format": None,
            }
        }
    }


class FieldTypeConfigUpdate(BaseModel):
    configured_type: FieldType = Field(..., description="Type to cast this field to")
    datetime_format: str | None = Field(
        default=None,
        description="strptime format string, only used when configured_type is datetime. Defaults to ISO 8601.",
    )


# =============================================================================
# RESPONSE SCHEMAS
# =============================================================================


class FieldTypeConfigResponse(BaseModel):
    field_name: str
    configured_type: str
    datetime_format: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class FieldTypeConfigListResponse(BaseModel):
    configs: list[FieldTypeConfigResponse]


class FieldTypeMutationResponse(BaseModel):
    success: bool
    message: str
    config: FieldTypeConfigResponse | None = None
    error: str | None = None


class FieldObservationResponse(BaseModel):
    field_name: str
    observed_json_type: str
    occurrence_count: int
    last_seen: datetime | None = None

    model_config = {"from_attributes": True}


class FieldObservationListResponse(BaseModel):
    observations: list[FieldObservationResponse]
