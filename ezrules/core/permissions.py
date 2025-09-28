from functools import wraps

from flask import abort, current_app
from flask_security import current_user

from ezrules.core.permissions_constants import PermissionAction
from ezrules.models.backend_core import Action, RoleActions
from ezrules.models.database import db_session


class PermissionManager:
    db_session = db_session

    @staticmethod
    def init_default_actions():
        default_actions = PermissionAction.get_default_actions()

        for name, description, resource_type in default_actions:
            if not PermissionManager.db_session.query(Action).filter_by(name=name).first():
                action = Action(name=name, description=description, resource_type=resource_type)
                PermissionManager.db_session.add(action)

        PermissionManager.db_session.commit()

    @staticmethod
    def user_has_permission(user, action_name: PermissionAction | str, resource_id: int | None = None) -> bool:
        if not user or not user.is_authenticated:
            return False

        # Check if any actions exist in the database - if not, permissions haven't been initialized
        # In this case, allow access for authenticated users (backward compatibility)
        actions_exist = PermissionManager.db_session.query(Action).first() is not None
        if not actions_exist:
            return True

        # Convert enum to string if needed
        action_str = action_name.value if isinstance(action_name, PermissionAction) else action_name

        action = PermissionManager.db_session.query(Action).filter_by(name=action_str).first()
        if not action:
            return False

        for role in user.roles:
            role_action = (
                PermissionManager.db_session.query(RoleActions)
                .filter_by(role_id=role.id, action_id=action.id)
                .filter((RoleActions.resource_id == resource_id) | (RoleActions.resource_id.is_(None)))
                .first()
            )
            if role_action:
                return True

        return False

    @staticmethod
    def grant_permission(role_id: int, action_name: PermissionAction | str, resource_id: int | None = None):
        # Convert enum to string if needed
        action_str = action_name.value if isinstance(action_name, PermissionAction) else action_name

        action = PermissionManager.db_session.query(Action).filter_by(name=action_str).first()
        if not action:
            raise ValueError(f"Action '{action_str}' not found")

        existing = (
            PermissionManager.db_session.query(RoleActions)
            .filter_by(role_id=role_id, action_id=action.id, resource_id=resource_id)
            .first()
        )

        if not existing:
            role_action = RoleActions(role_id=role_id, action_id=action.id, resource_id=resource_id)
            PermissionManager.db_session.add(role_action)
            PermissionManager.db_session.commit()

    @staticmethod
    def revoke_permission(role_id: int, action_name: PermissionAction | str, resource_id: int | None = None):
        # Convert enum to string if needed
        action_str = action_name.value if isinstance(action_name, PermissionAction) else action_name

        action = PermissionManager.db_session.query(Action).filter_by(name=action_str).first()
        if not action:
            raise ValueError(f"Action '{action_str}' not found")

        role_action = (
            PermissionManager.db_session.query(RoleActions)
            .filter_by(role_id=role_id, action_id=action.id, resource_id=resource_id)
            .first()
        )

        if role_action:
            PermissionManager.db_session.delete(role_action)
            PermissionManager.db_session.commit()


def requires_permission(action_name: PermissionAction | str, resource_id_param: str | None = None):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if current_app.config.get("TESTING", False):
                return f(*args, **kwargs)

            resource_id = None
            if resource_id_param:
                resource_id = kwargs.get(resource_id_param)

            if not PermissionManager.user_has_permission(current_user, action_name, resource_id):
                abort(403)

            return f(*args, **kwargs)

        return decorated_function

    return decorator
