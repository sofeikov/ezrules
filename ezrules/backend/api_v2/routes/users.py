"""
FastAPI routes for user management.

These endpoints provide CRUD operations for users and role assignments.
All endpoints require authentication and appropriate permissions.
"""

import uuid
from typing import Any

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, status

from ezrules.backend.api_v2.auth.dependencies import (
    get_current_active_user,
    get_db,
    require_permission,
)
from ezrules.backend.api_v2.schemas.users import (
    AssignRoleRequest,
    RoleAssignmentResponse,
    RoleResponse,
    UserCreate,
    UserListItem,
    UserMutationResponse,
    UserResponse,
    UsersListResponse,
    UserUpdate,
)
from ezrules.core.permissions_constants import PermissionAction
from ezrules.models.backend_core import Role, User

router = APIRouter(prefix="/api/v2/users", tags=["Users"])


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def user_to_response(user: User) -> UserResponse:
    """Convert a database user model to API response."""
    roles = [
        RoleResponse(
            id=int(role.id),
            name=str(role.name),
            description=role.description,
        )
        for role in user.roles
    ]

    # Cast datetime fields - they're either datetime or None
    last_login = user.last_login_at if user.last_login_at is not None else None
    current_login = user.current_login_at if user.current_login_at is not None else None

    return UserResponse(
        id=int(user.id),
        email=str(user.email),
        active=bool(user.active),
        roles=roles,
        last_login_at=last_login,  # type: ignore[arg-type]
        current_login_at=current_login,  # type: ignore[arg-type]
    )


def user_to_list_item(user: User) -> UserListItem:
    """Convert a database user model to list item response."""
    roles = [
        RoleResponse(
            id=int(role.id),
            name=str(role.name),
            description=role.description,
        )
        for role in user.roles
    ]

    return UserListItem(
        id=int(user.id),
        email=str(user.email),
        active=bool(user.active),
        roles=roles,
    )


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


# =============================================================================
# LIST USERS
# =============================================================================


@router.get("", response_model=UsersListResponse)
def list_users(
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.VIEW_USERS)),
    db: Any = Depends(get_db),
) -> UsersListResponse:
    """
    Get all users.

    Returns a list of all users with their roles.
    Requires VIEW_USERS permission.
    """
    users = db.query(User).all()
    users_data = [user_to_list_item(u) for u in users]
    return UsersListResponse(users=users_data)


# =============================================================================
# GET SINGLE USER
# =============================================================================


@router.get("/{user_id}", response_model=UserResponse)
def get_user(
    user_id: int,
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.VIEW_USERS)),
    db: Any = Depends(get_db),
) -> UserResponse:
    """
    Get a single user by ID.

    Returns full user details including roles.
    Requires VIEW_USERS permission.
    """
    target_user = db.query(User).filter(User.id == user_id).first()

    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with id {user_id} not found",
        )

    return user_to_response(target_user)


# =============================================================================
# CREATE USER
# =============================================================================


@router.post("", response_model=UserMutationResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    user_data: UserCreate,
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.CREATE_USER)),
    db: Any = Depends(get_db),
) -> UserMutationResponse:
    """
    Create a new user.

    Requires CREATE_USER permission.
    Email must be unique.
    """
    # Check if email already exists
    existing_user = db.query(User).filter(User.email == user_data.email).first()
    if existing_user:
        return UserMutationResponse(
            success=False,
            message="Email already exists",
            error=f"A user with email '{user_data.email}' already exists",
        )

    # Create the new user
    new_user = User(
        email=user_data.email,
        password=hash_password(user_data.password),
        active=True,
        fs_uniquifier=str(uuid.uuid4()),
    )

    # Assign roles if provided
    if user_data.role_ids:
        roles = db.query(Role).filter(Role.id.in_(user_data.role_ids)).all()
        if len(roles) != len(user_data.role_ids):
            found_ids = {r.id for r in roles}
            missing_ids = [rid for rid in user_data.role_ids if rid not in found_ids]
            return UserMutationResponse(
                success=False,
                message="Some roles not found",
                error=f"Role IDs not found: {missing_ids}",
            )
        new_user.roles = roles

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return UserMutationResponse(
        success=True,
        message="User created successfully",
        user=user_to_response(new_user),
    )


# =============================================================================
# UPDATE USER
# =============================================================================


@router.put("/{user_id}", response_model=UserMutationResponse)
def update_user(
    user_id: int,
    user_data: UserUpdate,
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.MODIFY_USER)),
    db: Any = Depends(get_db),
) -> UserMutationResponse:
    """
    Update an existing user.

    Requires MODIFY_USER permission.
    Cannot deactivate yourself.
    """
    target_user = db.query(User).filter(User.id == user_id).first()

    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with id {user_id} not found",
        )

    # Prevent self-deactivation
    if user_data.active is False and user.id == user_id:
        return UserMutationResponse(
            success=False,
            message="Cannot deactivate yourself",
            error="You cannot deactivate your own account",
        )

    # Update email if provided
    if user_data.email is not None:
        # Check if email already exists for another user
        existing = db.query(User).filter(User.email == user_data.email, User.id != user_id).first()
        if existing:
            return UserMutationResponse(
                success=False,
                message="Email already exists",
                error=f"A user with email '{user_data.email}' already exists",
            )
        target_user.email = user_data.email

    # Update password if provided
    if user_data.password is not None:
        target_user.password = hash_password(user_data.password)

    # Update active status if provided
    if user_data.active is not None:
        target_user.active = user_data.active

    db.commit()
    db.refresh(target_user)

    return UserMutationResponse(
        success=True,
        message="User updated successfully",
        user=user_to_response(target_user),
    )


# =============================================================================
# DELETE USER
# =============================================================================


@router.delete("/{user_id}", response_model=UserMutationResponse)
def delete_user(
    user_id: int,
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.DELETE_USER)),
    db: Any = Depends(get_db),
) -> UserMutationResponse:
    """
    Delete a user.

    Requires DELETE_USER permission.
    Cannot delete yourself.
    """
    # Prevent self-deletion
    if user.id == user_id:
        return UserMutationResponse(
            success=False,
            message="Cannot delete yourself",
            error="You cannot delete your own account",
        )

    target_user = db.query(User).filter(User.id == user_id).first()

    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with id {user_id} not found",
        )

    db.delete(target_user)
    db.commit()

    return UserMutationResponse(
        success=True,
        message="User deleted successfully",
    )


# =============================================================================
# ASSIGN ROLE TO USER
# =============================================================================


@router.post("/{user_id}/roles", response_model=RoleAssignmentResponse)
def assign_role(
    user_id: int,
    role_data: AssignRoleRequest,
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.MANAGE_USER_ROLES)),
    db: Any = Depends(get_db),
) -> RoleAssignmentResponse:
    """
    Assign a role to a user.

    Requires MANAGE_USER_ROLES permission.
    """
    target_user = db.query(User).filter(User.id == user_id).first()

    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with id {user_id} not found",
        )

    role = db.query(Role).filter(Role.id == role_data.role_id).first()

    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Role with id {role_data.role_id} not found",
        )

    # Check if user already has this role
    if role in target_user.roles:
        return RoleAssignmentResponse(
            success=False,
            message="Role already assigned",
            error=f"User already has role '{role.name}'",
            user=user_to_response(target_user),
        )

    target_user.roles.append(role)
    db.commit()
    db.refresh(target_user)

    return RoleAssignmentResponse(
        success=True,
        message=f"Role '{role.name}' assigned successfully",
        user=user_to_response(target_user),
    )


# =============================================================================
# REMOVE ROLE FROM USER
# =============================================================================


@router.delete("/{user_id}/roles/{role_id}", response_model=RoleAssignmentResponse)
def remove_role(
    user_id: int,
    role_id: int,
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.MANAGE_USER_ROLES)),
    db: Any = Depends(get_db),
) -> RoleAssignmentResponse:
    """
    Remove a role from a user.

    Requires MANAGE_USER_ROLES permission.
    """
    target_user = db.query(User).filter(User.id == user_id).first()

    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with id {user_id} not found",
        )

    role = db.query(Role).filter(Role.id == role_id).first()

    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Role with id {role_id} not found",
        )

    # Check if user has this role
    if role not in target_user.roles:
        return RoleAssignmentResponse(
            success=False,
            message="Role not assigned",
            error=f"User does not have role '{role.name}'",
            user=user_to_response(target_user),
        )

    target_user.roles.remove(role)
    db.commit()
    db.refresh(target_user)

    return RoleAssignmentResponse(
        success=True,
        message=f"Role '{role.name}' removed successfully",
        user=user_to_response(target_user),
    )
