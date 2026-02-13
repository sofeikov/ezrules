"""
Pydantic schemas for role and permission management API endpoints.

These schemas define the request/response format for the Roles API.
Pydantic automatically validates incoming data and serializes outgoing data.
"""

from pydantic import BaseModel, Field

# =============================================================================
# REQUEST SCHEMAS
# =============================================================================


class RoleCreate(BaseModel):
    """Schema for creating a new role."""

    name: str = Field(..., min_length=1, description="Unique role name")
    description: str | None = Field(default=None, description="Role description")

    model_config = {
        "json_schema_extra": {
            "example": {
                "name": "auditor",
                "description": "Can view audit trails and reports",
            }
        }
    }


class RoleUpdate(BaseModel):
    """Schema for updating an existing role.

    All fields are optional - only provided fields will be updated.
    """

    name: str | None = Field(default=None, min_length=1, description="New role name")
    description: str | None = Field(default=None, description="New role description")


class RolePermissionsUpdate(BaseModel):
    """Schema for updating role permissions.

    Replaces all existing permissions with the provided list.
    """

    permission_ids: list[int] = Field(..., description="List of permission (action) IDs to assign")

    model_config = {
        "json_schema_extra": {
            "example": {
                "permission_ids": [1, 2, 3, 5],
            }
        }
    }


# =============================================================================
# RESPONSE SCHEMAS
# =============================================================================


class PermissionResponse(BaseModel):
    """Permission/Action details returned from API."""

    id: int = Field(..., description="Permission ID")
    name: str = Field(..., description="Permission action name")
    description: str | None = Field(default=None, description="Permission description")
    resource_type: str | None = Field(default=None, description="Resource type this permission applies to")

    model_config = {"from_attributes": True}


class PermissionsListResponse(BaseModel):
    """Response for GET /permissions endpoint."""

    permissions: list[PermissionResponse]


class RoleResponse(BaseModel):
    """Full role details returned from API."""

    id: int = Field(..., description="Role ID")
    name: str = Field(..., description="Role name")
    description: str | None = Field(default=None, description="Role description")
    user_count: int = Field(default=0, description="Number of users with this role")
    permissions: list[PermissionResponse] = Field(default_factory=list, description="Assigned permissions")

    model_config = {"from_attributes": True}


class RoleListItem(BaseModel):
    """Abbreviated role info for list endpoints."""

    id: int
    name: str
    description: str | None = None
    user_count: int = 0

    model_config = {"from_attributes": True}


class RolesListResponse(BaseModel):
    """Response for GET /roles endpoint."""

    roles: list[RoleListItem]


class RoleMutationResponse(BaseModel):
    """Response for create/update/delete operations."""

    success: bool
    message: str
    role: RoleResponse | None = None
    error: str | None = None


class RolePermissionsResponse(BaseModel):
    """Response for permission operations."""

    success: bool
    message: str
    role: RoleResponse | None = None
    error: str | None = None
