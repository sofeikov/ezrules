"""
Helper functions for recording audit trail entries.

These functions create history records for user lists, outcomes, and labels
whenever mutations occur. They should be called from the API routes before
or after the mutation, depending on the action type.
"""

import datetime

from ezrules.models.backend_core import (
    LabelHistory,
    OutcomeHistory,
    RolePermissionHistory,
    UserAccountHistory,
    UserListHistory,
)


def save_user_list_history(
    db,
    ul_id: int,
    list_name: str,
    action: str,
    o_id: int,
    changed_by: str | None = None,
    details: str | None = None,
) -> None:
    """Record an audit entry for a user list action."""
    history = UserListHistory(
        ul_id=ul_id,
        list_name=list_name,
        action=action,
        details=details,
        o_id=o_id,
        changed=datetime.datetime.now(datetime.UTC),
        changed_by=changed_by,
    )
    db.add(history)


def save_outcome_history(
    db,
    ao_id: int,
    outcome_name: str,
    action: str,
    o_id: int,
    changed_by: str | None = None,
) -> None:
    """Record an audit entry for an outcome action."""
    history = OutcomeHistory(
        ao_id=ao_id,
        outcome_name=outcome_name,
        action=action,
        o_id=o_id,
        changed=datetime.datetime.now(datetime.UTC),
        changed_by=changed_by,
    )
    db.add(history)


def save_label_history(
    db,
    el_id: int,
    label: str,
    action: str,
    changed_by: str | None = None,
) -> None:
    """Record an audit entry for a label action."""
    history = LabelHistory(
        el_id=el_id,
        label=label,
        action=action,
        changed=datetime.datetime.now(datetime.UTC),
        changed_by=changed_by,
    )
    db.add(history)


def save_user_account_history(
    db,
    user_id: int,
    user_email: str,
    action: str,
    changed_by: str | None = None,
    details: str | None = None,
) -> None:
    """Record an audit entry for a user account action."""
    history = UserAccountHistory(
        user_id=user_id,
        user_email=user_email,
        action=action,
        details=details,
        changed=datetime.datetime.now(datetime.UTC),
        changed_by=changed_by,
    )
    db.add(history)


def save_role_history(
    db,
    role_id: int,
    role_name: str,
    action: str,
    changed_by: str | None = None,
    details: str | None = None,
) -> None:
    """Record an audit entry for a role or permission action."""
    history = RolePermissionHistory(
        role_id=role_id,
        role_name=role_name,
        action=action,
        details=details,
        changed=datetime.datetime.now(datetime.UTC),
        changed_by=changed_by,
    )
    db.add(history)
