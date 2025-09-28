"""
Application Context - Global dependency registry for the EZRules application.

This module provides a clean way to manage application-level dependencies like
database sessions, list providers, outcome managers, etc. without polluting
business logic classes with infrastructure concerns.
"""

from typing import Optional

from ezrules.core.user_lists import AbstractUserListManager, StaticUserListManager


class ApplicationContext:
    """
    Global application context that holds application-level dependencies.

    This is a singleton-like registry that allows clean dependency injection
    without coupling business logic to specific implementations.
    """

    _instance: Optional["ApplicationContext"] = None

    def __init__(self):
        self._user_list_manager: AbstractUserListManager = StaticUserListManager()
        self._organization_id: int | None = None

    @classmethod
    def get_instance(cls) -> "ApplicationContext":
        """Get the singleton application context instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls):
        """Reset the application context (useful for testing)."""
        cls._instance = None

    def set_user_list_manager(self, manager: AbstractUserListManager):
        """Set the user list manager for the application."""
        self._user_list_manager = manager

    def get_user_list_manager(self) -> AbstractUserListManager:
        """Get the current user list manager."""
        return self._user_list_manager

    def set_organization_id(self, org_id: int):
        """Set the current organization ID."""
        self._organization_id = org_id

    def get_organization_id(self) -> int | None:
        """Get the current organization ID."""
        return self._organization_id


# Convenience functions for easy access
def get_user_list_manager() -> AbstractUserListManager:
    """Get the current user list manager from application context."""
    return ApplicationContext.get_instance().get_user_list_manager()


def set_user_list_manager(manager: AbstractUserListManager):
    """Set the user list manager in application context."""
    ApplicationContext.get_instance().set_user_list_manager(manager)


def get_organization_id() -> int | None:
    """Get the current organization ID from application context."""
    return ApplicationContext.get_instance().get_organization_id()


def set_organization_id(org_id: int):
    """Set the organization ID in application context."""
    ApplicationContext.get_instance().set_organization_id(org_id)


def reset_context():
    """Reset the application context (useful for testing)."""
    ApplicationContext.reset()
