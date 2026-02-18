from enum import Enum


class PermissionAction(Enum):
    """Enumeration of all available permission actions in the system."""

    # Rule Management
    CREATE_RULE = "create_rule"
    MODIFY_RULE = "modify_rule"
    DELETE_RULE = "delete_rule"
    VIEW_RULES = "view_rules"

    # Outcome Management
    CREATE_OUTCOME = "create_outcome"
    MODIFY_OUTCOME = "modify_outcome"
    DELETE_OUTCOME = "delete_outcome"
    VIEW_OUTCOMES = "view_outcomes"

    # List Management
    CREATE_LIST = "create_list"
    MODIFY_LIST = "modify_list"
    DELETE_LIST = "delete_list"
    VIEW_LISTS = "view_lists"

    # Label Management (for transaction categorization)
    CREATE_LABEL = "create_label"
    MODIFY_LABEL = "modify_label"
    DELETE_LABEL = "delete_label"
    VIEW_LABELS = "view_labels"

    # Audit Access
    ACCESS_AUDIT_TRAIL = "access_audit_trail"

    # User Management (Admin only)
    VIEW_USERS = "view_users"
    CREATE_USER = "create_user"
    MODIFY_USER = "modify_user"
    DELETE_USER = "delete_user"
    MANAGE_USER_ROLES = "manage_user_roles"

    # Role Management (Admin only)
    VIEW_ROLES = "view_roles"
    CREATE_ROLE = "create_role"
    MODIFY_ROLE = "modify_role"
    DELETE_ROLE = "delete_role"
    MANAGE_PERMISSIONS = "manage_permissions"

    # Field Type Management
    VIEW_FIELD_TYPES = "view_field_types"
    MODIFY_FIELD_TYPES = "modify_field_types"
    DELETE_FIELD_TYPE = "delete_field_type"

    @classmethod
    def get_default_actions(cls):
        """Get list of (action_name, description, resource_type) tuples for initialization."""
        return [
            (cls.CREATE_RULE.value, "Create new rules", "rule"),
            (cls.MODIFY_RULE.value, "Modify existing rules", "rule"),
            (cls.DELETE_RULE.value, "Delete rules", "rule"),
            (cls.VIEW_RULES.value, "View rules", "rule"),
            (cls.CREATE_OUTCOME.value, "Create new outcomes", "outcome"),
            (cls.MODIFY_OUTCOME.value, "Modify existing outcomes", "outcome"),
            (cls.DELETE_OUTCOME.value, "Delete outcomes", "outcome"),
            (cls.VIEW_OUTCOMES.value, "View outcomes", "outcome"),
            (cls.CREATE_LIST.value, "Create new user lists", "list"),
            (cls.MODIFY_LIST.value, "Modify existing user lists", "list"),
            (cls.DELETE_LIST.value, "Delete user lists", "list"),
            (cls.VIEW_LISTS.value, "View user lists", "list"),
            (cls.CREATE_LABEL.value, "Create new transaction labels", "label"),
            (cls.MODIFY_LABEL.value, "Modify existing transaction labels", "label"),
            (cls.DELETE_LABEL.value, "Delete transaction labels", "label"),
            (cls.VIEW_LABELS.value, "View transaction labels", "label"),
            (cls.ACCESS_AUDIT_TRAIL.value, "Access audit trail and history", "audit"),
            (cls.VIEW_USERS.value, "View system users", "user"),
            (cls.CREATE_USER.value, "Create new users", "user"),
            (cls.MODIFY_USER.value, "Modify existing users", "user"),
            (cls.DELETE_USER.value, "Delete users", "user"),
            (cls.MANAGE_USER_ROLES.value, "Manage user role assignments", "user"),
            (cls.VIEW_ROLES.value, "View system roles", "role"),
            (cls.CREATE_ROLE.value, "Create new roles", "role"),
            (cls.MODIFY_ROLE.value, "Modify existing roles", "role"),
            (cls.DELETE_ROLE.value, "Delete roles", "role"),
            (cls.MANAGE_PERMISSIONS.value, "Manage role permissions", "permission"),
            (cls.VIEW_FIELD_TYPES.value, "View field type configurations and observations", "field_type"),
            (cls.MODIFY_FIELD_TYPES.value, "Create and update field type configurations", "field_type"),
            (cls.DELETE_FIELD_TYPE.value, "Delete field type configurations", "field_type"),
        ]


class RoleType(Enum):
    """Enumeration of default role types."""

    ADMIN = "admin"
    READONLY = "readonly"
    RULE_EDITOR = "rule_editor"

    @classmethod
    def get_role_permissions(cls, role_type):
        """Get list of permissions for a given role type."""
        if role_type == cls.ADMIN:
            return list(PermissionAction)
        elif role_type == cls.READONLY:
            return [
                PermissionAction.VIEW_RULES,
                PermissionAction.VIEW_OUTCOMES,
                PermissionAction.VIEW_LISTS,
                PermissionAction.VIEW_LABELS,
            ]
        elif role_type == cls.RULE_EDITOR:
            return [
                PermissionAction.CREATE_RULE,
                PermissionAction.MODIFY_RULE,
                PermissionAction.VIEW_RULES,
                PermissionAction.VIEW_OUTCOMES,
                PermissionAction.VIEW_LISTS,
                PermissionAction.CREATE_LABEL,
                PermissionAction.VIEW_LABELS,
                PermissionAction.VIEW_FIELD_TYPES,
            ]
        else:
            return []
