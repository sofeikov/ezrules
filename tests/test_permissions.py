from unittest.mock import Mock, patch

import pytest

from ezrules.core.permissions import PermissionManager, requires_permission
from ezrules.core.permissions_constants import PermissionAction, RoleType
from ezrules.models.backend_core import Action, Role, RoleActions, User


class TestPermissionAction:
    def test_enum_values(self):
        assert PermissionAction.CREATE_RULE.value == "create_rule"
        assert PermissionAction.VIEW_RULES.value == "view_rules"
        assert PermissionAction.ACCESS_AUDIT_TRAIL.value == "access_audit_trail"

    def test_get_default_actions(self):
        default_actions = PermissionAction.get_default_actions()
        assert len(default_actions) > 0  # Based on the defined actions

        # Check that all actions have the required format (name, description, resource_type)
        for action_tuple in default_actions:
            assert len(action_tuple) == 3
            name, description, resource_type = action_tuple
            assert isinstance(name, str)
            assert isinstance(description, str)
            assert isinstance(resource_type, str)

        # Check specific actions exist
        action_names = [action[0] for action in default_actions]
        assert "create_rule" in action_names
        assert "view_rules" in action_names
        assert "access_audit_trail" in action_names


class TestRoleType:
    def test_enum_values(self):
        assert RoleType.ADMIN.value == "admin"
        assert RoleType.READONLY.value == "readonly"
        assert RoleType.RULE_EDITOR.value == "rule_editor"

    def test_get_role_permissions_admin(self):
        permissions = RoleType.get_role_permissions(RoleType.ADMIN)
        assert len(permissions) == len(list(PermissionAction))
        assert PermissionAction.CREATE_RULE in permissions
        assert PermissionAction.DELETE_RULE in permissions

    def test_get_role_permissions_readonly(self):
        permissions = RoleType.get_role_permissions(RoleType.READONLY)
        expected = [
            PermissionAction.VIEW_RULES,
            PermissionAction.VIEW_OUTCOMES,
            PermissionAction.VIEW_LISTS,
            PermissionAction.VIEW_LABELS,
        ]
        assert permissions == expected

    def test_get_role_permissions_rule_editor(self):
        permissions = RoleType.get_role_permissions(RoleType.RULE_EDITOR)
        expected = [
            PermissionAction.CREATE_RULE,
            PermissionAction.MODIFY_RULE,
            PermissionAction.VIEW_RULES,
            PermissionAction.VIEW_OUTCOMES,
            PermissionAction.VIEW_LISTS,
            PermissionAction.CREATE_LABEL,
            PermissionAction.VIEW_LABELS,
        ]
        assert permissions == expected

    def test_get_role_permissions_unknown(self):
        permissions = RoleType.get_role_permissions("unknown_role")
        assert permissions == []


class TestRequiresPermissionDecorator:
    def test_decorator_allows_access_in_testing_mode(self):
        mock_app = Mock()
        mock_app.config.get.return_value = True  # TESTING = True

        @requires_permission("test_action")
        def test_function():
            return "success"

        with patch("ezrules.core.permissions.current_app", mock_app):
            result = test_function()
            assert result == "success"

    def test_decorator_checks_permission_in_non_testing_mode(self):
        mock_app = Mock()
        mock_app.config.get.return_value = False  # TESTING = False
        mock_user = Mock()

        @requires_permission("test_action")
        def test_function():
            return "success"

        with (
            patch("ezrules.core.permissions.current_app", mock_app),
            patch("ezrules.core.permissions.current_user", mock_user),
            patch.object(PermissionManager, "user_has_permission", return_value=True),
        ):
            result = test_function()
            assert result == "success"

    def test_decorator_aborts_without_permission(self):
        mock_app = Mock()
        mock_app.config.get.return_value = False  # TESTING = False
        mock_user = Mock()

        @requires_permission("test_action")
        def test_function():
            return "success"

        with (
            patch("ezrules.core.permissions.current_app", mock_app),
            patch("ezrules.core.permissions.current_user", mock_user),
            patch.object(PermissionManager, "user_has_permission", return_value=False),
            patch("ezrules.core.permissions.abort") as mock_abort,
        ):
            test_function()
            mock_abort.assert_called_once_with(403)

    def test_decorator_with_resource_id_param(self):
        mock_app = Mock()
        mock_app.config.get.return_value = False  # TESTING = False
        mock_user = Mock()

        @requires_permission("test_action", resource_id_param="rule_id")
        def test_function(rule_id=123):
            return "success"

        with (
            patch("ezrules.core.permissions.current_app", mock_app),
            patch("ezrules.core.permissions.current_user", mock_user),
            patch.object(PermissionManager, "user_has_permission", return_value=True) as mock_permission,
        ):
            result = test_function(rule_id=123)
            assert result == "success"
            mock_permission.assert_called_once_with(mock_user, "test_action", 123)


class TestPermissionManager:
    def test_init_default_actions(self, session):
        PermissionManager.db_session = session
        PermissionManager.init_default_actions()

        actions = session.query(Action).all()
        assert len(actions) > 0  # Should match number of default actions

        # Check specific actions were created
        create_rule_action = session.query(Action).filter_by(name="create_rule").first()
        assert create_rule_action is not None
        assert create_rule_action.description == "Create new rules"
        assert create_rule_action.resource_type == "rule"

    def test_init_default_actions_idempotent(self, session):
        PermissionManager.db_session = session

        # Run twice to ensure idempotency
        PermissionManager.init_default_actions()
        first_count = session.query(Action).count()

        PermissionManager.init_default_actions()
        second_count = session.query(Action).count()

        assert first_count == second_count

    def test_user_has_permission_unauthenticated(self, session):
        PermissionManager.db_session = session
        user = Mock()
        user.is_authenticated = False

        result = PermissionManager.user_has_permission(user, "test_action")
        assert result is False

    def test_user_has_permission_no_user(self, session):
        PermissionManager.db_session = session

        result = PermissionManager.user_has_permission(None, "test_action")
        assert result is False

    def test_user_has_permission_no_actions_exist(self, session):
        PermissionManager.db_session = session
        user = Mock()
        user.is_authenticated = True

        # No actions in database, should return True for backward compatibility
        result = PermissionManager.user_has_permission(user, "test_action")
        assert result is True

    def test_user_has_permission_with_string(self, session):
        PermissionManager.db_session = session
        user = session.query(User).first()
        role = Role(name="testrole")
        action = Action(name="test_action", description="View rules", resource_type="rule")

        session.add_all([role, action])
        session.commit()

        # Assign role to user
        user.roles.append(role)
        session.commit()

        # Initially, the user should not have the permission
        assert not PermissionManager.user_has_permission(user, "test_action")

        # Grant permission to the role
        role_action = RoleActions(role_id=role.id, action_id=action.id)
        session.add(role_action)
        session.commit()

        # Now the user should have the permission
        assert PermissionManager.user_has_permission(user, "test_action")

    def test_user_has_permission_different_enum_types(self, session):
        PermissionManager.db_session = session
        PermissionManager.init_default_actions()

        user = session.query(User).first()
        role = Role(name="testrole")
        session.add(role)
        session.commit()

        user.roles.append(role)
        session.commit()

        action = session.query(Action).filter_by(name="create_rule").first()
        role_action = RoleActions(role_id=role.id, action_id=action.id)
        session.add(role_action)
        session.commit()

        # Test with enum
        assert PermissionManager.user_has_permission(user, PermissionAction.CREATE_RULE)

        # Test with string
        assert PermissionManager.user_has_permission(user, "create_rule")

    def test_user_has_permission_mixed_enum_string(self, session):
        PermissionManager.db_session = session
        PermissionManager.init_default_actions()

        user = session.query(User).first()
        role = Role(name="testrole")
        session.add(role)
        session.commit()

        user.roles.append(role)
        session.commit()

        action = session.query(Action).filter_by(name="view_rules").first()
        role_action = RoleActions(role_id=role.id, action_id=action.id)
        session.add(role_action)
        session.commit()

        # Should work with enum
        assert PermissionManager.user_has_permission(user, PermissionAction.VIEW_RULES)

    def test_enum_to_string_conversion(self, session):
        PermissionManager.db_session = session
        PermissionManager.init_default_actions()

        user = session.query(User).first()
        role = Role(name="admin")
        session.add(role)
        session.commit()

        user.roles.append(role)
        session.commit()

        # Grant permission using enum
        PermissionManager.grant_permission(role.id, PermissionAction.CREATE_RULE)

        # Check permission with enum and string
        assert PermissionManager.user_has_permission(user, PermissionAction.CREATE_RULE)
        assert PermissionManager.user_has_permission(user, "create_rule")

    def test_permission_manager_accepts_enums(self, session):
        PermissionManager.db_session = session
        PermissionManager.init_default_actions()

        role = Role(name="test")
        session.add(role)
        session.commit()

        # Should work with enum
        PermissionManager.grant_permission(role.id, PermissionAction.VIEW_RULES)

        # Verify it was granted
        role_action = (
            session.query(RoleActions)
            .join(Action)
            .filter(RoleActions.role_id == role.id, Action.name == "view_rules")
            .first()
        )
        assert role_action is not None

    def test_grant_permission_string_action(self, session):
        PermissionManager.db_session = session
        PermissionManager.init_default_actions()

        role = Role(name="test")
        session.add(role)
        session.commit()

        # Grant permission
        PermissionManager.grant_permission(role.id, "create_rule")

        # Verify it was granted
        role_action = (
            session.query(RoleActions)
            .join(Action)
            .filter(RoleActions.role_id == role.id, Action.name == "create_rule")
            .first()
        )
        assert role_action is not None

    def test_grant_permission_enum_action(self, session):
        PermissionManager.db_session = session
        PermissionManager.init_default_actions()

        role = Role(name="test")
        session.add(role)
        session.commit()

        # Grant permission with enum
        PermissionManager.grant_permission(role.id, PermissionAction.VIEW_RULES)

        # Verify it was granted
        role_action = (
            session.query(RoleActions)
            .join(Action)
            .filter(RoleActions.role_id == role.id, Action.name == "view_rules")
            .first()
        )
        assert role_action is not None

    def test_grant_permission_with_resource_id(self, session):
        PermissionManager.db_session = session
        PermissionManager.init_default_actions()

        role = Role(name="test")
        session.add(role)
        session.commit()

        # Grant permission for specific resource
        PermissionManager.grant_permission(role.id, "create_rule", resource_id=123)

        # Verify it was granted with correct resource_id
        role_action = (
            session.query(RoleActions)
            .join(Action)
            .filter(RoleActions.role_id == role.id, Action.name == "create_rule", RoleActions.resource_id == 123)
            .first()
        )
        assert role_action is not None

    def test_grant_permission_idempotent(self, session):
        PermissionManager.db_session = session
        PermissionManager.init_default_actions()

        role = Role(name="test")
        session.add(role)
        session.commit()

        # Grant same permission twice
        PermissionManager.grant_permission(role.id, "create_rule")
        PermissionManager.grant_permission(role.id, "create_rule")

        # Should only have one record
        count = (
            session.query(RoleActions)
            .join(Action)
            .filter(RoleActions.role_id == role.id, Action.name == "create_rule")
            .count()
        )
        assert count == 1

    def test_grant_permission_nonexistent_action(self, session):
        PermissionManager.db_session = session

        role = Role(name="test")
        session.add(role)
        session.commit()

        # Should raise ValueError for nonexistent action
        with pytest.raises(ValueError, match="Action 'nonexistent' not found"):
            PermissionManager.grant_permission(role.id, "nonexistent")

    def test_revoke_permission_string_action(self, session):
        PermissionManager.db_session = session
        PermissionManager.init_default_actions()

        role = Role(name="test")
        session.add(role)
        session.commit()

        # Grant then revoke permission
        PermissionManager.grant_permission(role.id, "create_rule")
        PermissionManager.revoke_permission(role.id, "create_rule")

        # Verify it was revoked
        role_action = (
            session.query(RoleActions)
            .join(Action)
            .filter(RoleActions.role_id == role.id, Action.name == "create_rule")
            .first()
        )
        assert role_action is None

    def test_revoke_permission_enum_action(self, session):
        PermissionManager.db_session = session
        PermissionManager.init_default_actions()

        role = Role(name="test")
        session.add(role)
        session.commit()

        # Grant then revoke permission with enum
        PermissionManager.grant_permission(role.id, PermissionAction.VIEW_RULES)
        PermissionManager.revoke_permission(role.id, PermissionAction.VIEW_RULES)

        # Verify it was revoked
        role_action = (
            session.query(RoleActions)
            .join(Action)
            .filter(RoleActions.role_id == role.id, Action.name == "view_rules")
            .first()
        )
        assert role_action is None

    def test_revoke_permission_with_resource_id(self, session):
        PermissionManager.db_session = session
        PermissionManager.init_default_actions()

        role = Role(name="test")
        session.add(role)
        session.commit()

        # Grant then revoke permission for specific resource
        PermissionManager.grant_permission(role.id, "create_rule", resource_id=123)
        PermissionManager.revoke_permission(role.id, "create_rule", resource_id=123)

        # Verify it was revoked
        role_action = (
            session.query(RoleActions)
            .join(Action)
            .filter(RoleActions.role_id == role.id, Action.name == "create_rule", RoleActions.resource_id == 123)
            .first()
        )
        assert role_action is None

    def test_revoke_permission_nonexistent_action(self, session):
        PermissionManager.db_session = session

        role = Role(name="test")
        session.add(role)
        session.commit()

        # Should raise ValueError for nonexistent action
        with pytest.raises(ValueError, match="Action 'nonexistent' not found"):
            PermissionManager.revoke_permission(role.id, "nonexistent")

    def test_revoke_permission_nonexistent_role_action(self, session):
        PermissionManager.db_session = session
        PermissionManager.init_default_actions()

        role = Role(name="test")
        session.add(role)
        session.commit()

        # Should not raise error when revoking non-granted permission
        PermissionManager.revoke_permission(role.id, "create_rule")
        # Should pass without error

    def test_user_has_permission_with_resource_id_match(self, session):
        PermissionManager.db_session = session
        PermissionManager.init_default_actions()

        user = session.query(User).first()
        role = Role(name="test")
        session.add(role)
        session.commit()

        user.roles.append(role)
        session.commit()

        # Grant permission for specific resource
        PermissionManager.grant_permission(role.id, "create_rule", resource_id=123)

        # Should have permission for that resource
        assert PermissionManager.user_has_permission(user, "create_rule", resource_id=123)

        # Should not have permission for different resource
        assert not PermissionManager.user_has_permission(user, "create_rule", resource_id=456)

    def test_user_has_permission_global_permission(self, session):
        PermissionManager.db_session = session
        PermissionManager.init_default_actions()

        user = session.query(User).first()
        role = Role(name="test")
        session.add(role)
        session.commit()

        user.roles.append(role)
        session.commit()

        # Grant global permission (no resource_id)
        PermissionManager.grant_permission(role.id, "create_rule")

        # Should have permission for any resource
        assert PermissionManager.user_has_permission(user, "create_rule", resource_id=123)
        assert PermissionManager.user_has_permission(user, "create_rule", resource_id=456)
        assert PermissionManager.user_has_permission(user, "create_rule")

    def test_user_has_permission_nonexistent_action(self, session):
        PermissionManager.db_session = session
        PermissionManager.init_default_actions()

        user = session.query(User).first()

        # Should return False for nonexistent action
        assert not PermissionManager.user_has_permission(user, "nonexistent_action")
