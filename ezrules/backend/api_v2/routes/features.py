from datetime import datetime
from typing import Any, cast

from fastapi import APIRouter, Depends, HTTPException, status

from ezrules.backend.api_v2.auth.dependencies import (
    get_current_active_user,
    get_current_org_id,
    get_db,
    require_permission,
)
from ezrules.backend.api_v2.schemas.features import (
    ALLOWED_WINDOW_SECONDS,
    FeatureDefinitionCreate,
    FeatureDefinitionListResponse,
    FeatureDefinitionResponse,
    FeatureDefinitionUpdate,
    FeatureDependencyListResponse,
    FeatureDependencyResponse,
    FeatureFilter,
    FeatureMutationResponse,
    FeaturePreviewRequest,
    FeaturePreviewResponse,
    FeatureStatus,
)
from ezrules.backend.features import (
    MAX_ACTIVE_FEATURES_PER_ORG,
    compute_feature,
    feature_path,
    get_feature_dependencies,
)
from ezrules.core.audit_helpers import save_feature_definition_history
from ezrules.core.permissions_constants import PermissionAction
from ezrules.models.backend_core import FeatureDefinition, User

router = APIRouter(prefix="/api/v2/features", tags=["Features"])


def _response(db: Any, o_id: int, feature: FeatureDefinition) -> FeatureDefinitionResponse:
    stat_path = feature_path(feature)
    return FeatureDefinitionResponse(
        fd_id=int(feature.fd_id),
        name=str(feature.name),
        description=cast(str | None, feature.description),
        entity=str(feature.entity),
        feature_name=str(feature.feature_name),
        available_as=f"stat[{stat_path}]",
        entity_key=str(feature.entity_key),
        aggregation_type=str(feature.aggregation_type),
        source_field=cast(str | None, feature.source_field),
        window_seconds=int(feature.window_seconds),
        window_label=ALLOWED_WINDOW_SECONDS.get(int(feature.window_seconds), f"{feature.window_seconds}s"),
        filters=[FeatureFilter.model_validate(item) for item in cast(list[dict[str, Any]], feature.filters or [])],
        inclusion_policy=str(feature.inclusion_policy),
        null_handling=str(feature.null_handling),
        status=FeatureStatus(str(feature.status)),
        version=int(feature.version),
        dependency_count=len(get_feature_dependencies(db, o_id, stat_path)),
        created_at=cast(datetime, feature.created_at),
        updated_at=cast(datetime, feature.updated_at),
    )


def _apply_payload(feature: FeatureDefinition, data: FeatureDefinitionCreate | FeatureDefinitionUpdate) -> None:
    feature.name = data.name
    feature.description = data.description
    feature.entity = data.entity
    feature.feature_name = data.feature_name
    feature.entity_key = data.entity_key
    feature.aggregation_type = data.aggregation_type.value
    feature.source_field = data.source_field
    feature.window_seconds = data.window_seconds
    feature.filters = [filter_config.model_dump() for filter_config in data.filters]
    feature.inclusion_policy = data.inclusion_policy
    feature.null_handling = data.null_handling


def _get_feature(db: Any, o_id: int, feature_id: int) -> FeatureDefinition:
    feature = (
        db.query(FeatureDefinition)
        .filter(FeatureDefinition.o_id == o_id, FeatureDefinition.fd_id == feature_id)
        .first()
    )
    if feature is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Feature not found")
    return feature


def _ensure_unique_feature_path(
    db: Any,
    o_id: int,
    *,
    entity: str,
    feature_name: str,
    exclude_feature_id: int | None = None,
) -> None:
    query = db.query(FeatureDefinition).filter(
        FeatureDefinition.o_id == o_id,
        FeatureDefinition.entity == entity,
        FeatureDefinition.feature_name == feature_name,
    )
    if exclude_feature_id is not None:
        query = query.filter(FeatureDefinition.fd_id != exclude_feature_id)
    if query.first() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Feature path already exists")


@router.get("", response_model=FeatureDefinitionListResponse)
def list_features(
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.VIEW_FEATURES)),
    current_org_id: int = Depends(get_current_org_id),
    db: Any = Depends(get_db),
) -> FeatureDefinitionListResponse:
    features = (
        db.query(FeatureDefinition)
        .filter(FeatureDefinition.o_id == current_org_id)
        .order_by(FeatureDefinition.updated_at.desc(), FeatureDefinition.fd_id.desc())
        .all()
    )
    return FeatureDefinitionListResponse(features=[_response(db, current_org_id, feature) for feature in features])


@router.post("", response_model=FeatureMutationResponse, status_code=status.HTTP_201_CREATED)
def create_feature(
    data: FeatureDefinitionCreate,
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.MODIFY_FEATURES)),
    current_org_id: int = Depends(get_current_org_id),
    db: Any = Depends(get_db),
) -> FeatureMutationResponse:
    _ensure_unique_feature_path(db, current_org_id, entity=data.entity, feature_name=data.feature_name)

    feature = FeatureDefinition(o_id=current_org_id, created_by=str(user.email), updated_by=str(user.email))
    _apply_payload(feature, data)
    db.add(feature)
    db.flush()
    save_feature_definition_history(
        db,
        fd_id=int(feature.fd_id),
        entity=str(feature.entity),
        feature_name=str(feature.feature_name),
        action="created",
        version=int(feature.version),
        o_id=current_org_id,
        changed_by=str(user.email),
    )
    db.commit()
    db.refresh(feature)
    return FeatureMutationResponse(
        success=True, message="Feature created", feature=_response(db, current_org_id, feature)
    )


@router.put("/{feature_id}", response_model=FeatureMutationResponse)
def update_feature(
    feature_id: int,
    data: FeatureDefinitionUpdate,
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.MODIFY_FEATURES)),
    current_org_id: int = Depends(get_current_org_id),
    db: Any = Depends(get_db),
) -> FeatureMutationResponse:
    feature = _get_feature(db, current_org_id, feature_id)
    _ensure_unique_feature_path(
        db,
        current_org_id,
        entity=data.entity,
        feature_name=data.feature_name,
        exclude_feature_id=feature_id,
    )
    if feature.status == "active" and get_feature_dependencies(db, current_org_id, feature_path(feature)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Active features used by rules cannot be edited incompatibly; deprecate and create a new feature.",
        )
    _apply_payload(feature, data)
    feature.version = int(feature.version) + 1
    feature.updated_by = str(user.email)
    save_feature_definition_history(
        db,
        fd_id=int(feature.fd_id),
        entity=str(feature.entity),
        feature_name=str(feature.feature_name),
        action="updated",
        version=int(feature.version),
        o_id=current_org_id,
        changed_by=str(user.email),
    )
    db.commit()
    db.refresh(feature)
    return FeatureMutationResponse(
        success=True, message="Feature updated", feature=_response(db, current_org_id, feature)
    )


@router.post("/{feature_id}/activate", response_model=FeatureMutationResponse)
def activate_feature(
    feature_id: int,
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.MODIFY_FEATURES)),
    current_org_id: int = Depends(get_current_org_id),
    db: Any = Depends(get_db),
) -> FeatureMutationResponse:
    active_count = (
        db.query(FeatureDefinition)
        .filter(FeatureDefinition.o_id == current_org_id, FeatureDefinition.status == "active")
        .count()
    )
    if active_count >= MAX_ACTIVE_FEATURES_PER_ORG:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Active feature quota exceeded")
    feature = _get_feature(db, current_org_id, feature_id)
    feature.status = "active"
    feature.version = int(feature.version) + 1
    feature.updated_by = str(user.email)
    save_feature_definition_history(
        db,
        fd_id=int(feature.fd_id),
        entity=str(feature.entity),
        feature_name=str(feature.feature_name),
        action="activated",
        version=int(feature.version),
        o_id=current_org_id,
        changed_by=str(user.email),
    )
    db.commit()
    db.refresh(feature)
    return FeatureMutationResponse(
        success=True, message="Feature activated", feature=_response(db, current_org_id, feature)
    )


@router.post("/{feature_id}/deprecate", response_model=FeatureMutationResponse)
def deprecate_feature(
    feature_id: int,
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.MODIFY_FEATURES)),
    current_org_id: int = Depends(get_current_org_id),
    db: Any = Depends(get_db),
) -> FeatureMutationResponse:
    feature = _get_feature(db, current_org_id, feature_id)
    if get_feature_dependencies(db, current_org_id, feature_path(feature)):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Feature is used by rules")
    feature.status = "deprecated"
    feature.version = int(feature.version) + 1
    feature.updated_by = str(user.email)
    save_feature_definition_history(
        db,
        fd_id=int(feature.fd_id),
        entity=str(feature.entity),
        feature_name=str(feature.feature_name),
        action="deprecated",
        version=int(feature.version),
        o_id=current_org_id,
        changed_by=str(user.email),
    )
    db.commit()
    db.refresh(feature)
    return FeatureMutationResponse(
        success=True, message="Feature deprecated", feature=_response(db, current_org_id, feature)
    )


@router.delete("/{feature_id}", response_model=FeatureMutationResponse)
def delete_feature(
    feature_id: int,
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.DELETE_FEATURE)),
    current_org_id: int = Depends(get_current_org_id),
    db: Any = Depends(get_db),
) -> FeatureMutationResponse:
    feature = _get_feature(db, current_org_id, feature_id)
    dependencies = get_feature_dependencies(db, current_org_id, feature_path(feature))
    if dependencies:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Feature is used by rules")
    response = _response(db, current_org_id, feature)
    save_feature_definition_history(
        db,
        fd_id=int(feature.fd_id),
        entity=str(feature.entity),
        feature_name=str(feature.feature_name),
        action="deleted",
        version=int(feature.version),
        o_id=current_org_id,
        changed_by=str(user.email),
    )
    db.delete(feature)
    db.commit()
    return FeatureMutationResponse(success=True, message="Feature deleted", feature=response)


@router.post("/{feature_id}/preview", response_model=FeaturePreviewResponse)
def preview_feature(
    feature_id: int,
    request: FeaturePreviewRequest,
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.VIEW_FEATURES)),
    current_org_id: int = Depends(get_current_org_id),
    db: Any = Depends(get_db),
) -> FeaturePreviewResponse:
    feature = _get_feature(db, current_org_id, feature_id)
    result = compute_feature(db, current_org_id, feature, request.event_data, request.as_of)
    return FeaturePreviewResponse(
        value=result.value,
        matched_event_count=result.matched_event_count,
        as_of=result.as_of,
        window_start=result.window_start,
    )


@router.get("/{feature_id}/dependencies", response_model=FeatureDependencyListResponse)
def feature_dependencies(
    feature_id: int,
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.VIEW_FEATURES)),
    current_org_id: int = Depends(get_current_org_id),
    db: Any = Depends(get_db),
) -> FeatureDependencyListResponse:
    feature = _get_feature(db, current_org_id, feature_id)
    dependencies = get_feature_dependencies(db, current_org_id, feature_path(feature))
    return FeatureDependencyListResponse(
        dependencies=[
            FeatureDependencyResponse(
                r_id=int(rule.r_id),
                rid=str(rule.rid),
                description=str(rule.description),
                status=str(rule.status.value if hasattr(rule.status, "value") else rule.status),
            )
            for rule in dependencies
        ]
    )
