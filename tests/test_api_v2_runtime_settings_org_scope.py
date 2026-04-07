"""Org-scope coverage for active-rule auto-promotion runtime settings."""

import bcrypt

from fastapi.testclient import TestClient

from ezrules.backend.api_v2.auth.jwt import create_access_token
from ezrules.backend.api_v2.main import app
from ezrules.core.permissions import PermissionManager
from ezrules.core.permissions_constants import PermissionAction
from ezrules.models.backend_core import AllowedOutcome, Organisation, Role, RuntimeSetting, User


def _auth_headers(user: User) -> dict[str, str]:
    token = create_access_token(
        user_id=int(user.id),
        email=str(user.email),
        roles=[role.name for role in user.roles],
        org_id=int(user.o_id),
    )
    return {"Authorization": f"Bearer {token}"}


def test_auto_promote_runtime_setting_is_org_scoped(session):
    hashed_password = bcrypt.hashpw("orgscopepass".encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    org = Organisation(name="Org One")
    other_org = Organisation(name="Org Two")
    session.add_all([org, other_org])
    session.commit()

    role = Role(name="settings_scope_admin", description="Can manage settings", o_id=int(org.o_id))
    session.add(role)
    session.commit()

    user = User(
        email="settings-scope@example.com",
        password=hashed_password,
        active=True,
        fs_uniquifier="settings-scope@example.com",
        o_id=int(org.o_id),
    )
    user.roles.append(role)
    session.add(user)
    session.commit()

    PermissionManager.db_session = session
    PermissionManager.init_default_actions()
    PermissionManager.grant_permission(role.id, PermissionAction.VIEW_ROLES)
    PermissionManager.grant_permission(role.id, PermissionAction.MANAGE_PERMISSIONS)
    PermissionManager.grant_permission(role.id, PermissionAction.MANAGE_NEUTRAL_OUTCOME)

    session.add_all(
        [
            AllowedOutcome(outcome_name="RELEASE", severity_rank=1, o_id=int(org.o_id)),
            AllowedOutcome(outcome_name="HOLD", severity_rank=2, o_id=int(org.o_id)),
        ]
    )
    session.add(
        RuntimeSetting(
            key="auto_promote_active_rule_updates",
            o_id=int(other_org.o_id),
            value_type="bool",
            value="true",
        )
    )
    session.add(
        RuntimeSetting(
            key="neutral_outcome",
            o_id=int(other_org.o_id),
            value_type="string",
            value="HOLD",
        )
    )
    session.commit()

    with TestClient(app) as client:
        get_response = client.get("/api/v2/settings/runtime", headers=_auth_headers(user))
        update_response = client.put(
            "/api/v2/settings/runtime",
            headers=_auth_headers(user),
            json={
                "rule_quality_lookback_days": 21,
                "auto_promote_active_rule_updates": False,
                "neutral_outcome": "RELEASE",
            },
        )

    assert get_response.status_code == 200
    assert get_response.json()["auto_promote_active_rule_updates"] is False
    assert get_response.json()["neutral_outcome"] == "RELEASE"

    assert update_response.status_code == 200
    assert update_response.json()["auto_promote_active_rule_updates"] is False
    assert update_response.json()["neutral_outcome"] == "RELEASE"

    stored = (
        session.query(RuntimeSetting)
        .filter(RuntimeSetting.key.in_(["auto_promote_active_rule_updates", "neutral_outcome"]))
        .order_by(RuntimeSetting.o_id.asc(), RuntimeSetting.key.asc())
        .all()
    )
    assert [(int(item.o_id), str(item.key), str(item.value)) for item in stored] == [
        (int(org.o_id), "auto_promote_active_rule_updates", "false"),
        (int(org.o_id), "neutral_outcome", "RELEASE"),
        (int(other_org.o_id), "auto_promote_active_rule_updates", "true"),
        (int(other_org.o_id), "neutral_outcome", "HOLD"),
    ]
