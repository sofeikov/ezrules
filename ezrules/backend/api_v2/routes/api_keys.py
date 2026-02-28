"""
FastAPI routes for API key management.

These endpoints allow administrators to create, list, and revoke API keys
that can be used for service-to-service authentication with the evaluate endpoint.
"""

import datetime
import hashlib
import secrets
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ezrules.backend.api_v2.auth.dependencies import (
    get_current_active_user,
    get_db,
    require_permission,
)
from ezrules.core.application_context import get_organization_id
from ezrules.core.audit_helpers import save_api_key_history
from ezrules.core.permissions_constants import PermissionAction
from ezrules.models.backend_core import ApiKey, User
from ezrules.settings import app_settings

router = APIRouter(prefix="/api/v2/api-keys", tags=["API Keys"])


# =============================================================================
# SCHEMAS
# =============================================================================


class CreateApiKeyRequest(BaseModel):
    label: str


class ApiKeyResponse(BaseModel):
    gid: str
    label: str
    created_at: datetime.datetime
    revoked_at: datetime.datetime | None

    model_config = {"from_attributes": True}


class CreateApiKeyResponse(ApiKeyResponse):
    raw_key: str


# =============================================================================
# ENDPOINTS
# =============================================================================


@router.post("", response_model=CreateApiKeyResponse, status_code=status.HTTP_201_CREATED)
def create_api_key(
    request_data: CreateApiKeyRequest,
    db: Any = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.MANAGE_API_KEYS)),
) -> CreateApiKeyResponse:
    """
    Create a new API key.

    The raw key is returned exactly once. Store it securely — it cannot be retrieved again.
    """
    o_id = get_organization_id() or app_settings.ORG_ID
    raw_key = "ezrk_" + secrets.token_hex(32)
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    gid = str(uuid.uuid4())

    api_key = ApiKey(
        gid=gid,
        key_hash=key_hash,
        label=request_data.label,
        o_id=o_id,
    )
    db.add(api_key)
    db.flush()

    save_api_key_history(
        db=db,
        api_key_gid=gid,
        label=request_data.label,
        action="created",
        o_id=o_id,
        changed_by=str(current_user.email),
    )

    db.commit()
    db.refresh(api_key)

    return CreateApiKeyResponse(
        gid=str(api_key.gid),
        label=str(api_key.label),
        created_at=api_key.created_at,  # type: ignore[arg-type]
        revoked_at=api_key.revoked_at,  # type: ignore[arg-type]
        raw_key=raw_key,
    )


@router.get("", response_model=list[ApiKeyResponse])
def list_api_keys(
    db: Any = Depends(get_db),
    _: None = Depends(require_permission(PermissionAction.MANAGE_API_KEYS)),
) -> list[ApiKeyResponse]:
    """
    List all active (non-revoked) API keys for the organisation.

    Raw key values are never returned.
    """
    o_id = get_organization_id() or app_settings.ORG_ID
    keys = db.query(ApiKey).filter(ApiKey.o_id == o_id, ApiKey.revoked_at.is_(None)).all()
    return [
        ApiKeyResponse(
            gid=str(k.gid),
            label=str(k.label),
            created_at=k.created_at,  # type: ignore[arg-type]
            revoked_at=k.revoked_at,  # type: ignore[arg-type]
        )
        for k in keys
    ]


@router.delete("/{gid}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_api_key(
    gid: str,
    db: Any = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.MANAGE_API_KEYS)),
) -> None:
    """
    Revoke an API key by its GID.

    Sets revoked_at to the current timestamp. The row is retained for audit purposes.
    Subsequent authenticate attempts with this key will return 401.
    """
    o_id = get_organization_id() or app_settings.ORG_ID
    api_key = db.query(ApiKey).filter(ApiKey.gid == gid, ApiKey.o_id == o_id).first()
    if api_key is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found",
        )
    if api_key.revoked_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="API key is already revoked",
        )
    api_key.revoked_at = datetime.datetime.utcnow()

    save_api_key_history(
        db=db,
        api_key_gid=gid,
        label=str(api_key.label),
        action="revoked",
        o_id=o_id,
        changed_by=str(current_user.email),
    )

    db.commit()
