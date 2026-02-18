"""
FastAPI routes for field type configuration management.

These endpoints allow users to configure how event fields are cast before
rule evaluation, and to view auto-discovered field observations.
All endpoints require authentication and appropriate permissions.
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from ezrules.backend.api_v2.auth.dependencies import (
    get_current_active_user,
    get_db,
    require_permission,
)
from ezrules.backend.api_v2.schemas.field_types import (
    FieldObservationListResponse,
    FieldObservationResponse,
    FieldTypeConfigCreate,
    FieldTypeConfigListResponse,
    FieldTypeConfigResponse,
    FieldTypeConfigUpdate,
    FieldTypeMutationResponse,
)
from ezrules.core.permissions_constants import PermissionAction
from ezrules.models.backend_core import FieldObservation, FieldTypeConfig, User

router = APIRouter(prefix="/api/v2/field-types", tags=["Field Types"])

_DEFAULT_O_ID = 1


# =============================================================================
# LIST CONFIGS
# =============================================================================


@router.get("", response_model=FieldTypeConfigListResponse)
def list_field_type_configs(
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.VIEW_FIELD_TYPES)),
    db: Any = Depends(get_db),
) -> FieldTypeConfigListResponse:
    """Return all configured field types for the organisation."""
    configs = db.query(FieldTypeConfig).filter(FieldTypeConfig.o_id == _DEFAULT_O_ID).all()
    return FieldTypeConfigListResponse(configs=[FieldTypeConfigResponse.model_validate(c) for c in configs])


# =============================================================================
# LIST OBSERVATIONS
# =============================================================================


@router.get("/observations", response_model=FieldObservationListResponse)
def list_field_observations(
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.VIEW_FIELD_TYPES)),
    db: Any = Depends(get_db),
) -> FieldObservationListResponse:
    """Return all auto-discovered field observations for the organisation."""
    observations = db.query(FieldObservation).filter(FieldObservation.o_id == _DEFAULT_O_ID).all()
    return FieldObservationListResponse(observations=[FieldObservationResponse.model_validate(o) for o in observations])


# =============================================================================
# CREATE / UPSERT CONFIG
# =============================================================================


@router.post("", response_model=FieldTypeMutationResponse, status_code=status.HTTP_201_CREATED)
def upsert_field_type_config(
    data: FieldTypeConfigCreate,
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.MODIFY_FIELD_TYPES)),
    db: Any = Depends(get_db),
) -> FieldTypeMutationResponse:
    """Create or update a field type configuration."""
    existing = (
        db.query(FieldTypeConfig)
        .filter(FieldTypeConfig.field_name == data.field_name, FieldTypeConfig.o_id == _DEFAULT_O_ID)
        .first()
    )

    if existing:
        existing.configured_type = data.configured_type.value
        existing.datetime_format = data.datetime_format
        db.commit()
        db.refresh(existing)
        return FieldTypeMutationResponse(
            success=True,
            message=f"Field type config for '{data.field_name}' updated",
            config=FieldTypeConfigResponse.model_validate(existing),
        )

    new_config = FieldTypeConfig(
        field_name=data.field_name,
        configured_type=data.configured_type.value,
        datetime_format=data.datetime_format,
        o_id=_DEFAULT_O_ID,
    )
    db.add(new_config)
    db.commit()
    db.refresh(new_config)

    return FieldTypeMutationResponse(
        success=True,
        message=f"Field type config for '{data.field_name}' created",
        config=FieldTypeConfigResponse.model_validate(new_config),
    )


# =============================================================================
# UPDATE CONFIG
# =============================================================================


@router.put("/{field_name}", response_model=FieldTypeMutationResponse)
def update_field_type_config(
    field_name: str,
    data: FieldTypeConfigUpdate,
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.MODIFY_FIELD_TYPES)),
    db: Any = Depends(get_db),
) -> FieldTypeMutationResponse:
    """Update the type or datetime format for an existing field config."""
    config = (
        db.query(FieldTypeConfig)
        .filter(FieldTypeConfig.field_name == field_name, FieldTypeConfig.o_id == _DEFAULT_O_ID)
        .first()
    )

    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No config found for field '{field_name}'",
        )

    config.configured_type = data.configured_type.value
    config.datetime_format = data.datetime_format
    db.commit()
    db.refresh(config)

    return FieldTypeMutationResponse(
        success=True,
        message=f"Field type config for '{field_name}' updated",
        config=FieldTypeConfigResponse.model_validate(config),
    )


# =============================================================================
# DELETE CONFIG
# =============================================================================


@router.delete("/{field_name}", response_model=FieldTypeMutationResponse)
def delete_field_type_config(
    field_name: str,
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.DELETE_FIELD_TYPE)),
    db: Any = Depends(get_db),
) -> FieldTypeMutationResponse:
    """Delete a field type configuration (field reverts to compare-as-is)."""
    config = (
        db.query(FieldTypeConfig)
        .filter(FieldTypeConfig.field_name == field_name, FieldTypeConfig.o_id == _DEFAULT_O_ID)
        .first()
    )

    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No config found for field '{field_name}'",
        )

    db.delete(config)
    db.commit()

    return FieldTypeMutationResponse(
        success=True,
        message=f"Field type config for '{field_name}' deleted",
    )
