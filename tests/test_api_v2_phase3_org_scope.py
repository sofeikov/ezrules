import uuid

from fastapi.testclient import TestClient

from ezrules.backend.api_v2.auth.jwt import create_access_token
from ezrules.backend.api_v2.main import app
from ezrules.core.permissions import PermissionManager
from ezrules.core.permissions_constants import PermissionAction
from ezrules.models.backend_core import (
    AllowedOutcome,
    Label,
    LabelHistory,
    Organisation,
    Role,
    RolePermissionHistory,
    Rule,
    RuleBackTestingResult,
    User,
    UserAccountHistory,
)


def _unique_email(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}@example.com"


def _create_org(session, prefix: str) -> Organisation:
    org = Organisation(name=f"{prefix}-{uuid.uuid4().hex[:8]}")
    session.add(org)
    session.commit()
    session.refresh(org)
    return org


def _grant_permissions(session, role: Role, permissions: list[PermissionAction]) -> None:
    PermissionManager.db_session = session
    PermissionManager.init_default_actions()
    for permission in permissions:
        PermissionManager.grant_permission(int(role.id), permission)


def _create_user(
    session,
    *,
    org_id: int,
    permissions: list[PermissionAction],
    email_prefix: str,
) -> User:
    role = Role(
        name=f"phase3-role-{uuid.uuid4().hex[:8]}",
        description="Phase 3 org-scoped role",
        o_id=org_id,
    )
    session.add(role)
    session.commit()
    _grant_permissions(session, role, permissions)

    user = User(
        email=_unique_email(email_prefix),
        password="phase3pass",
        active=True,
        fs_uniquifier=str(uuid.uuid4()),
        o_id=org_id,
    )
    user.roles.append(role)
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def _auth_headers(user: User) -> dict[str, str]:
    token = create_access_token(
        user_id=int(user.id),
        email=str(user.email),
        roles=[str(role.name) for role in user.roles],
        org_id=int(user.o_id),
    )
    return {"Authorization": f"Bearer {token}"}


def test_roles_are_org_scoped_and_reject_cross_org_assignment(session):
    org = session.query(Organisation).one()
    other_org = _create_org(session, "phase3-roles")
    admin = _create_user(
        session,
        org_id=int(org.o_id),
        permissions=[
            PermissionAction.VIEW_ROLES,
            PermissionAction.CREATE_ROLE,
            PermissionAction.VIEW_USERS,
            PermissionAction.MANAGE_USER_ROLES,
        ],
        email_prefix="phase3-roles-admin",
    )
    target_user = User(
        email=_unique_email("phase3-target"),
        password="phase3pass",
        active=True,
        fs_uniquifier=str(uuid.uuid4()),
        o_id=int(org.o_id),
    )
    other_org_role = Role(name="ORG2_ONLY_ROLE", description="Other org role", o_id=int(other_org.o_id))
    session.add_all([target_user, other_org_role])
    session.commit()

    with TestClient(app) as client:
        create_response = client.post(
            "/api/v2/roles",
            headers=_auth_headers(admin),
            json={"name": "ORG2_ONLY_ROLE", "description": "Org 1 copy"},
        )
        assert create_response.status_code == 201
        assert create_response.json()["role"]["description"] == "Org 1 copy"

        list_response = client.get("/api/v2/roles", headers=_auth_headers(admin))
        assert list_response.status_code == 200
        role_descriptions = {item["description"] for item in list_response.json()["roles"]}
        assert "Org 1 copy" in role_descriptions
        assert "Other org role" not in role_descriptions

        assign_response = client.post(
            f"/api/v2/users/{int(target_user.id)}/roles",
            headers=_auth_headers(admin),
            json={"role_id": int(other_org_role.id)},
        )
        assert assign_response.status_code == 404


def test_labels_and_rule_quality_options_are_org_scoped(session):
    org = session.query(Organisation).one()
    other_org = _create_org(session, "phase3-labels")
    admin = _create_user(
        session,
        org_id=int(org.o_id),
        permissions=[
            PermissionAction.VIEW_LABELS,
            PermissionAction.CREATE_LABEL,
            PermissionAction.VIEW_ROLES,
        ],
        email_prefix="phase3-labels-admin",
    )
    session.add_all(
        [
            Label(label="OTHER_ONLY_LABEL", o_id=int(other_org.o_id)),
            Label(label="SHARED_LABEL", o_id=int(other_org.o_id)),
            AllowedOutcome(outcome_name="RELEASE", severity_rank=1, o_id=int(org.o_id)),
        ]
    )
    session.commit()

    with TestClient(app) as client:
        create_response = client.post(
            "/api/v2/labels",
            headers=_auth_headers(admin),
            json={"label_name": "shared_label"},
        )
        assert create_response.status_code == 201
        assert create_response.json()["success"] is True

        list_response = client.get("/api/v2/labels", headers=_auth_headers(admin))
        assert list_response.status_code == 200
        label_names = {item["label"] for item in list_response.json()["labels"]}
        assert "SHARED_LABEL" in label_names
        assert "OTHER_ONLY_LABEL" not in label_names

        options_response = client.get(
            "/api/v2/settings/rule-quality-pairs/options",
            headers=_auth_headers(admin),
        )
        assert options_response.status_code == 200
        options = options_response.json()
        assert "SHARED_LABEL" in options["labels"]
        assert "OTHER_ONLY_LABEL" not in options["labels"]


def test_audit_history_endpoints_filter_by_org(session):
    org = session.query(Organisation).one()
    other_org = _create_org(session, "phase3-audit")
    audit_user = _create_user(
        session,
        org_id=int(org.o_id),
        permissions=[PermissionAction.ACCESS_AUDIT_TRAIL],
        email_prefix="phase3-audit-admin",
    )
    session.add_all(
        [
            LabelHistory(el_id=1, label="ORG1_LABEL", action="created", o_id=int(org.o_id), changed_by="org1"),
            LabelHistory(el_id=2, label="ORG2_LABEL", action="created", o_id=int(other_org.o_id), changed_by="org2"),
            UserAccountHistory(
                user_id=10,
                user_email="org1@example.com",
                action="created",
                o_id=int(org.o_id),
                changed_by="org1",
            ),
            UserAccountHistory(
                user_id=20,
                user_email="org2@example.com",
                action="created",
                o_id=int(other_org.o_id),
                changed_by="org2",
            ),
            RolePermissionHistory(
                role_id=100,
                role_name="ORG1_ROLE",
                action="created",
                o_id=int(org.o_id),
                changed_by="org1",
            ),
            RolePermissionHistory(
                role_id=200,
                role_name="ORG2_ROLE",
                action="created",
                o_id=int(other_org.o_id),
                changed_by="org2",
            ),
        ]
    )
    session.commit()

    with TestClient(app) as client:
        summary_response = client.get("/api/v2/audit", headers=_auth_headers(audit_user))
        assert summary_response.status_code == 200
        summary = summary_response.json()
        assert summary["total_label_actions"] == 1
        assert summary["total_user_account_actions"] == 1
        assert summary["total_role_permission_actions"] == 1

        labels_response = client.get("/api/v2/audit/labels", headers=_auth_headers(audit_user))
        assert labels_response.status_code == 200
        assert labels_response.json()["total"] == 1
        assert labels_response.json()["items"][0]["label"] == "ORG1_LABEL"

        users_response = client.get("/api/v2/audit/users", headers=_auth_headers(audit_user))
        assert users_response.status_code == 200
        assert users_response.json()["total"] == 1
        assert users_response.json()["items"][0]["user_email"] == "org1@example.com"

        roles_response = client.get("/api/v2/audit/roles", headers=_auth_headers(audit_user))
        assert roles_response.status_code == 200
        assert roles_response.json()["total"] == 1
        assert roles_response.json()["items"][0]["role_name"] == "ORG1_ROLE"


def test_backtesting_endpoints_hide_other_org_rules(session):
    org = session.query(Organisation).one()
    other_org = _create_org(session, "phase3-backtesting")
    user = _create_user(
        session,
        org_id=int(org.o_id),
        permissions=[PermissionAction.VIEW_RULES, PermissionAction.MODIFY_RULE],
        email_prefix="phase3-backtesting-admin",
    )
    other_rule = Rule(
        rid="PHASE3:OTHER",
        logic='return "HOLD"',
        description="Other org rule",
        o_id=int(other_org.o_id),
    )
    session.add(other_rule)
    session.commit()
    session.add(RuleBackTestingResult(r_id=int(other_rule.r_id), task_id="phase3-task"))
    session.commit()

    with TestClient(app) as client:
        trigger_response = client.post(
            "/api/v2/backtesting",
            headers=_auth_headers(user),
            json={"r_id": int(other_rule.r_id), "new_rule_logic": 'return "BLOCK"'},
        )
        assert trigger_response.status_code == 404

        results_response = client.get(
            f"/api/v2/backtesting/{int(other_rule.r_id)}",
            headers=_auth_headers(user),
        )
        assert results_response.status_code == 404
