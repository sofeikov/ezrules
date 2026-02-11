"""
FastAPI routes for user lists management.

These endpoints provide CRUD operations for user lists and their entries.
User lists are used in rule logic (e.g., "if country in HighRiskCountries").
All endpoints require authentication and appropriate permissions.
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from ezrules.backend.api_v2.auth.dependencies import (
    get_current_active_user,
    get_db,
    require_permission,
)
from ezrules.backend.api_v2.schemas.user_lists import (
    UserListCreate,
    UserListDetailResponse,
    UserListEntryBulkCreate,
    UserListEntryBulkResponse,
    UserListEntryCreate,
    UserListEntryMutationResponse,
    UserListEntryResponse,
    UserListMutationResponse,
    UserListResponse,
    UserListsListResponse,
    UserListUpdate,
)
from ezrules.core.audit_helpers import save_user_list_history
from ezrules.core.permissions_constants import PermissionAction
from ezrules.models.backend_core import User, UserList, UserListEntry

router = APIRouter(prefix="/api/v2/user-lists", tags=["User Lists"])

# Default organization ID (in multi-tenant setup, this would come from user context)
DEFAULT_ORG_ID = 1


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def list_to_response(user_list: UserList) -> UserListResponse:
    """Convert a database user list model to API response."""
    entry_count = len(user_list.entries) if user_list.entries else 0
    created_at = user_list.created_at if user_list.created_at is not None else None

    return UserListResponse(
        id=int(user_list.ul_id),
        name=str(user_list.list_name),
        entry_count=entry_count,
        created_at=created_at,  # type: ignore[arg-type]
    )


def list_to_detail_response(user_list: UserList) -> UserListDetailResponse:
    """Convert a database user list model to detailed API response with entries."""
    entries = [
        UserListEntryResponse(
            id=int(entry.ule_id),
            value=str(entry.entry_value),
            created_at=entry.created_at if entry.created_at is not None else None,  # type: ignore[arg-type]
        )
        for entry in user_list.entries
    ]
    created_at = user_list.created_at if user_list.created_at is not None else None

    return UserListDetailResponse(
        id=int(user_list.ul_id),
        name=str(user_list.list_name),
        entry_count=len(entries),
        created_at=created_at,  # type: ignore[arg-type]
        entries=entries,
    )


def entry_to_response(entry: UserListEntry) -> UserListEntryResponse:
    """Convert a database entry model to API response."""
    created_at = entry.created_at if entry.created_at is not None else None

    return UserListEntryResponse(
        id=int(entry.ule_id),
        value=str(entry.entry_value),
        created_at=created_at,  # type: ignore[arg-type]
    )


# =============================================================================
# LIST ALL USER LISTS
# =============================================================================


@router.get("", response_model=UserListsListResponse)
def list_user_lists(
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.VIEW_LISTS)),
    db: Any = Depends(get_db),
) -> UserListsListResponse:
    """
    Get all user lists.

    Returns a list of all user lists with entry counts.
    Requires VIEW_LISTS permission.
    """
    lists = db.query(UserList).filter(UserList.o_id == DEFAULT_ORG_ID).all()
    lists_data = [list_to_response(ul) for ul in lists]
    return UserListsListResponse(lists=lists_data)


# =============================================================================
# GET SINGLE USER LIST
# =============================================================================


@router.get("/{list_id}", response_model=UserListDetailResponse)
def get_user_list(
    list_id: int,
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.VIEW_LISTS)),
    db: Any = Depends(get_db),
) -> UserListDetailResponse:
    """
    Get a single user list with all entries.

    Returns full list details including all entries.
    Requires VIEW_LISTS permission.
    """
    user_list = (
        db.query(UserList)
        .filter(
            UserList.ul_id == list_id,
            UserList.o_id == DEFAULT_ORG_ID,
        )
        .first()
    )

    if not user_list:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User list with id {list_id} not found",
        )

    return list_to_detail_response(user_list)


# =============================================================================
# CREATE USER LIST
# =============================================================================


@router.post("", response_model=UserListMutationResponse, status_code=status.HTTP_201_CREATED)
def create_user_list(
    list_data: UserListCreate,
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.CREATE_LIST)),
    db: Any = Depends(get_db),
) -> UserListMutationResponse:
    """
    Create a new user list.

    The list name is used in rule logic (e.g., "if country in HighRiskCountries").
    Requires CREATE_LIST permission.
    """
    # Check if list name already exists
    existing = (
        db.query(UserList)
        .filter(
            UserList.list_name == list_data.name,
            UserList.o_id == DEFAULT_ORG_ID,
        )
        .first()
    )

    if existing:
        return UserListMutationResponse(
            success=False,
            message="List name already exists",
            error=f"A list with name '{list_data.name}' already exists",
        )

    # Create the new list
    new_list = UserList(
        list_name=list_data.name,
        o_id=DEFAULT_ORG_ID,
    )

    db.add(new_list)
    db.commit()
    db.refresh(new_list)

    save_user_list_history(
        db,
        ul_id=int(new_list.ul_id),
        list_name=str(new_list.list_name),
        action="created",
        o_id=DEFAULT_ORG_ID,
        changed_by=str(user.email) if user.email else None,
    )
    db.commit()

    return UserListMutationResponse(
        success=True,
        message="User list created successfully",
        list=list_to_response(new_list),
    )


# =============================================================================
# UPDATE USER LIST
# =============================================================================


@router.put("/{list_id}", response_model=UserListMutationResponse)
def update_user_list(
    list_id: int,
    list_data: UserListUpdate,
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.MODIFY_LIST)),
    db: Any = Depends(get_db),
) -> UserListMutationResponse:
    """
    Update a user list (rename).

    Requires MODIFY_LIST permission.
    """
    user_list = (
        db.query(UserList)
        .filter(
            UserList.ul_id == list_id,
            UserList.o_id == DEFAULT_ORG_ID,
        )
        .first()
    )

    if not user_list:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User list with id {list_id} not found",
        )

    # Check if new name already exists
    if list_data.name is not None:
        existing = (
            db.query(UserList)
            .filter(
                UserList.list_name == list_data.name,
                UserList.o_id == DEFAULT_ORG_ID,
                UserList.ul_id != list_id,
            )
            .first()
        )

        if existing:
            return UserListMutationResponse(
                success=False,
                message="List name already exists",
                error=f"A list with name '{list_data.name}' already exists",
            )

        old_name = user_list.list_name
        user_list.list_name = list_data.name

        save_user_list_history(
            db,
            ul_id=user_list.ul_id,
            list_name=list_data.name,
            action="renamed",
            o_id=DEFAULT_ORG_ID,
            changed_by=str(user.email) if user.email else None,
            details=f"Renamed from '{old_name}' to '{list_data.name}'",
        )

    db.commit()
    db.refresh(user_list)

    return UserListMutationResponse(
        success=True,
        message="User list updated successfully",
        list=list_to_response(user_list),
    )


# =============================================================================
# DELETE USER LIST
# =============================================================================


@router.delete("/{list_id}", response_model=UserListMutationResponse)
def delete_user_list(
    list_id: int,
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.DELETE_LIST)),
    db: Any = Depends(get_db),
) -> UserListMutationResponse:
    """
    Delete a user list and all its entries.

    Requires DELETE_LIST permission.
    Warning: This will break any rules referencing this list!
    """
    user_list = (
        db.query(UserList)
        .filter(
            UserList.ul_id == list_id,
            UserList.o_id == DEFAULT_ORG_ID,
        )
        .first()
    )

    if not user_list:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User list with id {list_id} not found",
        )

    list_name = user_list.list_name
    ul_id = user_list.ul_id

    save_user_list_history(
        db,
        ul_id=ul_id,
        list_name=list_name,
        action="deleted",
        o_id=DEFAULT_ORG_ID,
        changed_by=str(user.email) if user.email else None,
    )

    # Entries will be cascade deleted due to relationship configuration
    db.delete(user_list)
    db.commit()

    return UserListMutationResponse(
        success=True,
        message=f"User list '{list_name}' deleted successfully",
    )


# =============================================================================
# GET LIST ENTRIES
# =============================================================================


@router.get("/{list_id}/entries", response_model=UserListDetailResponse)
def get_list_entries(
    list_id: int,
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.VIEW_LISTS)),
    db: Any = Depends(get_db),
) -> UserListDetailResponse:
    """
    Get all entries for a user list.

    Requires VIEW_LISTS permission.
    """
    user_list = (
        db.query(UserList)
        .filter(
            UserList.ul_id == list_id,
            UserList.o_id == DEFAULT_ORG_ID,
        )
        .first()
    )

    if not user_list:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User list with id {list_id} not found",
        )

    return list_to_detail_response(user_list)


# =============================================================================
# ADD ENTRY TO LIST
# =============================================================================


@router.post("/{list_id}/entries", response_model=UserListEntryMutationResponse, status_code=status.HTTP_201_CREATED)
def add_entry(
    list_id: int,
    entry_data: UserListEntryCreate,
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.MODIFY_LIST)),
    db: Any = Depends(get_db),
) -> UserListEntryMutationResponse:
    """
    Add an entry to a user list.

    Requires MODIFY_LIST permission.
    """
    user_list = (
        db.query(UserList)
        .filter(
            UserList.ul_id == list_id,
            UserList.o_id == DEFAULT_ORG_ID,
        )
        .first()
    )

    if not user_list:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User list with id {list_id} not found",
        )

    # Check if entry already exists
    existing = (
        db.query(UserListEntry)
        .filter(
            UserListEntry.ul_id == list_id,
            UserListEntry.entry_value == entry_data.value,
        )
        .first()
    )

    if existing:
        return UserListEntryMutationResponse(
            success=False,
            message="Entry already exists",
            error=f"Value '{entry_data.value}' already exists in this list",
            entry=entry_to_response(existing),
        )

    # Create the new entry
    new_entry = UserListEntry(
        entry_value=entry_data.value,
        ul_id=list_id,
    )

    db.add(new_entry)

    save_user_list_history(
        db,
        ul_id=list_id,
        list_name=str(user_list.list_name),
        action="entry_added",
        o_id=DEFAULT_ORG_ID,
        changed_by=str(user.email) if user.email else None,
        details=f"Added entry '{entry_data.value}'",
    )

    db.commit()
    db.refresh(new_entry)

    return UserListEntryMutationResponse(
        success=True,
        message="Entry added successfully",
        entry=entry_to_response(new_entry),
    )


# =============================================================================
# BULK ADD ENTRIES
# =============================================================================


@router.post("/{list_id}/entries/bulk", response_model=UserListEntryBulkResponse, status_code=status.HTTP_201_CREATED)
def bulk_add_entries(
    list_id: int,
    bulk_data: UserListEntryBulkCreate,
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.MODIFY_LIST)),
    db: Any = Depends(get_db),
) -> UserListEntryBulkResponse:
    """
    Bulk add entries to a user list.

    Useful for CSV import. Skips existing entries.
    Requires MODIFY_LIST permission.
    """
    user_list = (
        db.query(UserList)
        .filter(
            UserList.ul_id == list_id,
            UserList.o_id == DEFAULT_ORG_ID,
        )
        .first()
    )

    if not user_list:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User list with id {list_id} not found",
        )

    added = []
    skipped = []

    for value in bulk_data.values:
        # Check if entry already exists
        existing = (
            db.query(UserListEntry)
            .filter(
                UserListEntry.ul_id == list_id,
                UserListEntry.entry_value == value,
            )
            .first()
        )

        if existing:
            skipped.append(value)
        else:
            new_entry = UserListEntry(
                entry_value=value,
                ul_id=list_id,
            )
            db.add(new_entry)
            added.append(value)

    if added:
        save_user_list_history(
            db,
            ul_id=list_id,
            list_name=str(user_list.list_name),
            action="entries_bulk_added",
            o_id=DEFAULT_ORG_ID,
            changed_by=str(user.email) if user.email else None,
            details=f"Added {len(added)} entries, skipped {len(skipped)}",
        )

    db.commit()

    return UserListEntryBulkResponse(
        success=True,
        message=f"Added {len(added)} entries, skipped {len(skipped)} existing",
        added=added,
        skipped=skipped,
    )


# =============================================================================
# DELETE ENTRY
# =============================================================================


@router.delete("/{list_id}/entries/{entry_id}", response_model=UserListEntryMutationResponse)
def delete_entry(
    list_id: int,
    entry_id: int,
    user: User = Depends(get_current_active_user),
    _: None = Depends(require_permission(PermissionAction.MODIFY_LIST)),
    db: Any = Depends(get_db),
) -> UserListEntryMutationResponse:
    """
    Delete an entry from a user list.

    Requires MODIFY_LIST permission.
    """
    # First verify the list exists
    user_list = (
        db.query(UserList)
        .filter(
            UserList.ul_id == list_id,
            UserList.o_id == DEFAULT_ORG_ID,
        )
        .first()
    )

    if not user_list:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User list with id {list_id} not found",
        )

    # Find the entry
    entry = (
        db.query(UserListEntry)
        .filter(
            UserListEntry.ule_id == entry_id,
            UserListEntry.ul_id == list_id,
        )
        .first()
    )

    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Entry with id {entry_id} not found in list {list_id}",
        )

    entry_value = entry.entry_value

    save_user_list_history(
        db,
        ul_id=list_id,
        list_name=str(user_list.list_name),
        action="entry_removed",
        o_id=DEFAULT_ORG_ID,
        changed_by=str(user.email) if user.email else None,
        details=f"Removed entry '{entry_value}'",
    )

    db.delete(entry)
    db.commit()

    return UserListEntryMutationResponse(
        success=True,
        message=f"Entry '{entry_value}' deleted successfully",
    )
