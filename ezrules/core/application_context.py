"""
Request-local application context for organisation-scoped dependencies.

This module exposes lightweight setters/getters for the active organisation ID
and user-list manager. Values are stored in ``ContextVar`` instances so request
handlers can safely run concurrently without leaking tenant state across
requests.
"""

from contextvars import ContextVar

from ezrules.core.user_lists import AbstractUserListManager, StaticUserListManager

_DEFAULT_USER_LIST_MANAGER: AbstractUserListManager = StaticUserListManager()

_user_list_manager_var: ContextVar[AbstractUserListManager | None] = ContextVar("ezrules_user_list_manager")
_organization_id_var: ContextVar[int | None] = ContextVar("ezrules_organization_id")


def get_user_list_manager() -> AbstractUserListManager:
    """Get the current user list manager from request-local context."""
    try:
        manager = _user_list_manager_var.get()
    except LookupError:
        return _DEFAULT_USER_LIST_MANAGER
    return manager or _DEFAULT_USER_LIST_MANAGER


def set_user_list_manager(manager: AbstractUserListManager) -> None:
    """Bind the user list manager in request-local context."""
    _user_list_manager_var.set(manager)


def get_organization_id() -> int | None:
    """Get the current organisation ID from request-local context."""
    try:
        return _organization_id_var.get()
    except LookupError:
        return None


def set_organization_id(org_id: int) -> None:
    """Bind the organisation ID in request-local context."""
    _organization_id_var.set(org_id)


def reset_context() -> None:
    """Reset request-local context to safe defaults."""
    _user_list_manager_var.set(None)
    _organization_id_var.set(None)
