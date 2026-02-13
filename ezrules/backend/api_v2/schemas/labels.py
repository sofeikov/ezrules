"""
Pydantic schemas for label-related API endpoints.

These schemas define the request/response format for the Labels API.
Pydantic automatically validates incoming data and serializes outgoing data.
"""

from pydantic import BaseModel, Field

# =============================================================================
# REQUEST SCHEMAS
# =============================================================================


class LabelCreate(BaseModel):
    """Schema for creating a new label."""

    label_name: str = Field(
        ...,
        min_length=1,
        description="Name of the label (will be converted to uppercase)",
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "label_name": "SUSPICIOUS",
            }
        }
    }


class LabelBulkCreate(BaseModel):
    """Schema for creating multiple labels at once."""

    labels: list[str] = Field(
        ...,
        min_length=1,
        description="List of label names to create",
    )


class MarkEventRequest(BaseModel):
    """Schema for marking an event with a label."""

    event_id: str = Field(..., description="The event ID to mark")
    label_name: str = Field(..., description="The label name to apply")

    model_config = {
        "json_schema_extra": {
            "example": {
                "event_id": "evt_123456",
                "label_name": "FRAUD",
            }
        }
    }


# =============================================================================
# RESPONSE SCHEMAS
# =============================================================================


class LabelResponse(BaseModel):
    """Single label details returned from API."""

    el_id: int = Field(..., description="Database primary key")
    label: str = Field(..., description="Label name (uppercase)")

    model_config = {"from_attributes": True}


class LabelListItem(BaseModel):
    """Abbreviated label info for list endpoints."""

    el_id: int
    label: str

    model_config = {"from_attributes": True}


class LabelsListResponse(BaseModel):
    """Response for GET /labels endpoint."""

    labels: list[LabelListItem]


class LabelMutationResponse(BaseModel):
    """Response for create/delete operations."""

    success: bool
    message: str
    label: LabelResponse | None = None
    error: str | None = None


class LabelBulkCreateResponse(BaseModel):
    """Response for bulk label creation."""

    success: bool
    message: str
    created: list[str] = Field(default_factory=list)
    failed: list[str] = Field(default_factory=list)


class MarkEventResponse(BaseModel):
    """Response for marking an event with a label."""

    success: bool
    message: str
    event_id: str | None = None
    label_name: str | None = None
    error: str | None = None


class UploadResultError(BaseModel):
    """Single error from CSV upload."""

    row: int
    error: str


class UploadResult(BaseModel):
    """Response for CSV label upload."""

    total_rows: int
    successful: int
    failed: int
    errors: list[UploadResultError] = Field(default_factory=list)
