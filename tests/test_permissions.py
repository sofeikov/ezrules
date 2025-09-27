from ezrules.core.permissions import PermissionManager
from ezrules.models.backend_core import Action, Role, RoleActions, User


def test_can_init_defaults(session):
    from ezrules.core.permissions import PermissionManager

    PermissionManager.init_default_actions()
    actions = session.query(Action).all()
    assert len(actions) > 0


def test_user_has_permission(session):
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
