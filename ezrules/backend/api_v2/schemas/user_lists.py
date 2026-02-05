"""
Pydantic schemas for user lists management API endpoints.

These schemas define the request/response format for the User Lists API.
User lists are used in rule logic (e.g., "if country in HighRiskCountries").
"""

from datetime import datetime

from pydantic import BaseModel, Field

# =============================================================================
# REQUEST SCHEMAS
# =============================================================================


class UserListCreate(BaseModel):
    """Schema for creating a new user list."""

    name: str = Field(..., min_length=1, description="Unique list name (used in rule logic)")

    model_config = {
        "json_schema_extra": {
            "example": {
                "name": "HighRiskCountries",
            }
        }
    }


class UserListUpdate(BaseModel):
    """Schema for updating a user list."""

    name: str | None = Field(default=None, min_length=1, description="New list name")


class UserListEntryCreate(BaseModel):
    """Schema for adding an entry to a list."""

    value: str = Field(..., min_length=1, description="Entry value to add")

    model_config = {
        "json_schema_extra": {
            "example": {
                "value": "KZ",
            }
        }
    }


class UserListEntryBulkCreate(BaseModel):
    """Schema for bulk adding entries to a list."""

    values: list[str] = Field(..., min_length=1, description="List of values to add")

    model_config = {
        "json_schema_extra": {
            "example": {
                "values": ["KZ", "UZ", "KG", "TJ", "TM"],
            }
        }
    }


# =============================================================================
# RESPONSE SCHEMAS
# =============================================================================


class UserListEntryResponse(BaseModel):
    """Entry details returned from API."""

    id: int = Field(..., description="Entry ID")
    value: str = Field(..., description="Entry value")
    created_at: datetime | None = Field(default=None, description="When the entry was created")

    model_config = {"from_attributes": True}


class UserListResponse(BaseModel):
    """Full user list details returned from API."""

    id: int = Field(..., description="List ID")
    name: str = Field(..., description="List name (used in rule logic)")
    entry_count: int = Field(default=0, description="Number of entries in the list")
    created_at: datetime | None = Field(default=None, description="When the list was created")

    model_config = {"from_attributes": True}


class UserListDetailResponse(BaseModel):
    """User list with entries."""

    id: int = Field(..., description="List ID")
    name: str = Field(..., description="List name")
    entry_count: int = Field(default=0, description="Number of entries")
    created_at: datetime | None = Field(default=None, description="When created")
    entries: list[UserListEntryResponse] = Field(default_factory=list, description="List entries")


class UserListsListResponse(BaseModel):
    """Response for GET /user-lists endpoint."""

    lists: list[UserListResponse]


class UserListMutationResponse(BaseModel):
    """Response for create/update/delete operations on lists."""

    success: bool
    message: str
    list: UserListResponse | None = None
    error: str | None = None


class UserListEntryMutationResponse(BaseModel):
    """Response for entry operations."""

    success: bool
    message: str
    entry: UserListEntryResponse | None = None
    error: str | None = None


class UserListEntryBulkResponse(BaseModel):
    """Response for bulk entry operations."""

    success: bool
    message: str
    added: list[str] = Field(default_factory=list)
    skipped: list[str] = Field(default_factory=list, description="Already existing entries")
