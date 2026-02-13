"""
FastAPI routes for role and permission management.

These endpoints provide CRUD operations for roles and permission assignments.
All endpoints require authentication and appropriate permissions.
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from ezrules.backend.api_v2.auth.dependencies import (
    get_current_active_user,
    get_db,
    require_permission,
)
from ezrules.backend.api_v2.schemas.roles import (
    PermissionResponse,
    PermissionsListResponse,
    RoleCreate,
    RoleListItem,
    RoleMutationResponse,
    RolePermissionsResponse,
    RolePermissionsUpdate,
    RoleResponse,
    RolesListResponse,
    RoleUpdate,
)
from ezrules.core.audit_helpers import save_role_history
from ezrules.core.permissions_constants import PermissionAction
from ezrules.models.backend_core import Action, Role, RoleActions, User

router = APIRouter(prefix="/api/v2/roles", tags=["Roles"])

# Protected role names that cannot be deleted or renamed
PROTECTED_ROLES = {"admin", "readonly", "rule_editor"}


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def get_role_permissions(role: Role, db: Any) -> list[PermissionResponse]:
    """Get list of permissions for a role."""
    role_actions = db.query(RoleActions).filter(RoleActions.role_id == role.id).all()
    action_ids = [ra.action_id for ra in role_actions]

    if not action_ids:
        return []

    actions = db.query(Action).filter(Action.id.in_(action_ids)).all()
    return [
        PermissionResponse(
            id=int(action.id),
            name=str(action.name),
            description=action.description,
            resource_type=action.resource_type,
        )
        for action in actions
    ]


def role_to_response(role: Role, db: Any) -> RoleResponse:
    """Convert a database role model to API response."""
    user_count = len(list(role.users))
    permissions = get_role_permissions(role, db)
    # Cast description - it's either a string or None
    description = str(role.description) if role.description is not None else None

    return RoleResponse(
        id=int(role.id),
        name=str(role.name),
        description=description,
        user_count=user_count,
        permissions=permissions,
    )


def role_to_list_item(role: Role) -> RoleListItem:
    """Convert a database role model to list item response."""
    user_count = len(list(role.users))
    # Cast description - it's either a string or None
    description = str(role.description) if role.description is not None else None

    return RoleListItem(
        id=int(role.id),
        name=str(role.name),
        description=description,
        user_count=user_count,
    )


# =============================================================================
# LIST ALL PERMISSIONS
# =============================================================================


@router.get("/permissions", response_model=PermissionsListResponse)
def list_permissions(
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.VIEW_ROLES)),
    db: Any = Depends(get_db),
) -> PermissionsListResponse:
    """
    Get all available permissions.

    Returns a list of all permission actions that can be assigned to roles.
    Requires VIEW_ROLES permission.
    """
    actions = db.query(Action).order_by(Action.resource_type, Action.name).all()

    permissions = [
        PermissionResponse(
            id=int(action.id),
            name=str(action.name),
            description=action.description,
            resource_type=action.resource_type,
        )
        for action in actions
    ]

    return PermissionsListResponse(permissions=permissions)


# =============================================================================
# LIST ROLES
# =============================================================================


@router.get("", response_model=RolesListResponse)
def list_roles(
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.VIEW_ROLES)),
    db: Any = Depends(get_db),
) -> RolesListResponse:
    """
    Get all roles.

    Returns a list of all roles with user counts.
    Requires VIEW_ROLES permission.
    """
    roles = db.query(Role).all()
    roles_data = [role_to_list_item(r) for r in roles]
    return RolesListResponse(roles=roles_data)


# =============================================================================
# GET SINGLE ROLE
# =============================================================================


@router.get("/{role_id}", response_model=RoleResponse)
def get_role(
    role_id: int,
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.VIEW_ROLES)),
    db: Any = Depends(get_db),
) -> RoleResponse:
    """
    Get a single role by ID.

    Returns full role details including permissions.
    Requires VIEW_ROLES permission.
    """
    role = db.query(Role).filter(Role.id == role_id).first()

    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Role with id {role_id} not found",
        )

    return role_to_response(role, db)


# =============================================================================
# CREATE ROLE
# =============================================================================


@router.post("", response_model=RoleMutationResponse, status_code=status.HTTP_201_CREATED)
def create_role(
    role_data: RoleCreate,
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.CREATE_ROLE)),
    db: Any = Depends(get_db),
) -> RoleMutationResponse:
    """
    Create a new role.

    Requires CREATE_ROLE permission.
    Role name must be unique.
    """
    # Check if role name already exists
    existing_role = db.query(Role).filter(Role.name == role_data.name).first()
    if existing_role:
        return RoleMutationResponse(
            success=False,
            message="Role name already exists",
            error=f"A role with name '{role_data.name}' already exists",
        )

    # Create the new role
    new_role = Role(
        name=role_data.name,
        description=role_data.description,
    )

    db.add(new_role)
    db.commit()
    db.refresh(new_role)

    save_role_history(
        db, role_id=int(new_role.id), role_name=str(new_role.name), action="created", changed_by=str(user.email)
    )
    db.commit()

    return RoleMutationResponse(
        success=True,
        message="Role created successfully",
        role=role_to_response(new_role, db),
    )


# =============================================================================
# UPDATE ROLE
# =============================================================================


@router.put("/{role_id}", response_model=RoleMutationResponse)
def update_role(
    role_id: int,
    role_data: RoleUpdate,
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.MODIFY_ROLE)),
    db: Any = Depends(get_db),
) -> RoleMutationResponse:
    """
    Update an existing role.

    Requires MODIFY_ROLE permission.
    Protected roles (admin, readonly, rule_editor) cannot be renamed.
    """
    role = db.query(Role).filter(Role.id == role_id).first()

    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Role with id {role_id} not found",
        )

    # Check if trying to rename a protected role
    if role_data.name is not None and role.name in PROTECTED_ROLES and role_data.name != role.name:
        return RoleMutationResponse(
            success=False,
            message="Cannot rename protected role",
            error=f"Role '{role.name}' is a protected system role and cannot be renamed",
        )

    # Check if new name already exists
    changes: list[str] = []
    if role_data.name is not None:
        existing = db.query(Role).filter(Role.name == role_data.name, Role.id != role_id).first()
        if existing:
            return RoleMutationResponse(
                success=False,
                message="Role name already exists",
                error=f"A role with name '{role_data.name}' already exists",
            )
        if role_data.name != role.name:
            changes.append(f"name changed to {role_data.name}")
        role.name = role_data.name

    # Update description if provided
    if role_data.description is not None:
        if role_data.description != role.description:
            changes.append("description updated")
        role.description = role_data.description

    db.commit()
    db.refresh(role)

    if changes:
        save_role_history(
            db,
            role_id=int(role.id),
            role_name=str(role.name),
            action="updated",
            changed_by=str(user.email),
            details="; ".join(changes),
        )
        db.commit()

    return RoleMutationResponse(
        success=True,
        message="Role updated successfully",
        role=role_to_response(role, db),
    )


# =============================================================================
# DELETE ROLE
# =============================================================================


@router.delete("/{role_id}", response_model=RoleMutationResponse)
def delete_role(
    role_id: int,
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.DELETE_ROLE)),
    db: Any = Depends(get_db),
) -> RoleMutationResponse:
    """
    Delete a role.

    Requires DELETE_ROLE permission.
    Protected roles (admin, readonly, rule_editor) cannot be deleted.
    Roles with assigned users cannot be deleted.
    """
    role = db.query(Role).filter(Role.id == role_id).first()

    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Role with id {role_id} not found",
        )

    # Check if role is protected
    if role.name in PROTECTED_ROLES:
        return RoleMutationResponse(
            success=False,
            message="Cannot delete protected role",
            error=f"Role '{role.name}' is a protected system role and cannot be deleted",
        )

    # Check if role has assigned users
    user_count = len(list(role.users))
    if user_count > 0:
        return RoleMutationResponse(
            success=False,
            message="Cannot delete role with assigned users",
            error=f"Role '{role.name}' has {user_count} assigned user(s). Remove users from role first.",
        )

    # Record audit before deletion
    save_role_history(db, role_id=int(role.id), role_name=str(role.name), action="deleted", changed_by=str(user.email))

    # Delete role actions first
    db.query(RoleActions).filter(RoleActions.role_id == role_id).delete()

    # Delete the role
    db.delete(role)
    db.commit()

    return RoleMutationResponse(
        success=True,
        message="Role deleted successfully",
    )


# =============================================================================
# GET ROLE PERMISSIONS
# =============================================================================


@router.get("/{role_id}/permissions", response_model=RolePermissionsResponse)
def get_role_permissions_endpoint(
    role_id: int,
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.VIEW_ROLES)),
    db: Any = Depends(get_db),
) -> RolePermissionsResponse:
    """
    Get permissions assigned to a role.

    Requires VIEW_ROLES permission.
    """
    role = db.query(Role).filter(Role.id == role_id).first()

    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Role with id {role_id} not found",
        )

    return RolePermissionsResponse(
        success=True,
        message="Permissions retrieved successfully",
        role=role_to_response(role, db),
    )


# =============================================================================
# UPDATE ROLE PERMISSIONS
# =============================================================================


@router.put("/{role_id}/permissions", response_model=RolePermissionsResponse)
def update_role_permissions(
    role_id: int,
    permissions_data: RolePermissionsUpdate,
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.MANAGE_PERMISSIONS)),
    db: Any = Depends(get_db),
) -> RolePermissionsResponse:
    """
    Update permissions for a role.

    Replaces all existing permissions with the provided list.
    Requires MANAGE_PERMISSIONS permission.
    """
    role = db.query(Role).filter(Role.id == role_id).first()

    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Role with id {role_id} not found",
        )

    # Validate all permission IDs exist
    if permissions_data.permission_ids:
        actions = db.query(Action).filter(Action.id.in_(permissions_data.permission_ids)).all()
        if len(actions) != len(permissions_data.permission_ids):
            found_ids = {a.id for a in actions}
            missing_ids = [pid for pid in permissions_data.permission_ids if pid not in found_ids]
            return RolePermissionsResponse(
                success=False,
                message="Some permissions not found",
                error=f"Permission IDs not found: {missing_ids}",
            )

    # Capture old permission IDs before replacement
    old_role_actions = db.query(RoleActions).filter(RoleActions.role_id == role_id).all()
    old_action_ids = {ra.action_id for ra in old_role_actions}
    new_action_ids = set(permissions_data.permission_ids)

    # Remove all existing permissions for this role
    db.query(RoleActions).filter(RoleActions.role_id == role_id).delete()

    # Add new permissions
    for permission_id in permissions_data.permission_ids:
        role_action = RoleActions(role_id=role_id, action_id=permission_id)
        db.add(role_action)

    db.commit()
    db.refresh(role)

    # Build added/removed summary
    added_ids = new_action_ids - old_action_ids
    removed_ids = old_action_ids - new_action_ids
    all_relevant_ids = added_ids | removed_ids
    action_name_map: dict[int, str] = {}
    if all_relevant_ids:
        actions_list = db.query(Action).filter(Action.id.in_(all_relevant_ids)).all()
        action_name_map = {int(a.id): str(a.name) for a in actions_list}

    detail_parts: list[str] = []
    if added_ids:
        added_names = ", ".join(action_name_map.get(aid, str(aid)) for aid in sorted(added_ids))
        detail_parts.append(f"added: {added_names}")
    if removed_ids:
        removed_names = ", ".join(action_name_map.get(rid, str(rid)) for rid in sorted(removed_ids))
        detail_parts.append(f"removed: {removed_names}")
    if not detail_parts:
        detail_parts.append("no changes")
    details = "; ".join(detail_parts)

    save_role_history(
        db,
        role_id=int(role.id),
        role_name=str(role.name),
        action="permissions_updated",
        changed_by=str(user.email),
        details=details,
    )
    db.commit()

    return RolePermissionsResponse(
        success=True,
        message=f"Updated permissions for role '{role.name}'",
        role=role_to_response(role, db),
    )
