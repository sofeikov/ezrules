"""Tests for updating active rules with optional auto-promotion."""

from datetime import UTC, datetime

import bcrypt

import pytest
from fastapi.testclient import TestClient

from ezrules.backend.api_v2.auth.jwt import create_access_token
from ezrules.backend.api_v2.main import app
from ezrules.core.permissions import PermissionManager
from ezrules.core.permissions_constants import PermissionAction
from ezrules.core.rule_updater import RDBRuleEngineConfigProducer, RDBRuleManager
from ezrules.models.backend_core import (
    Organisation,
    Role,
    RuleEngineConfig,
    RuleHistory,
    RuleStatus,
    RuntimeSetting,
    User,
)
from ezrules.models.backend_core import Rule as RuleModel


def _ensure_org(session) -> Organisation:
    org = session.query(Organisation).filter(Organisation.o_id == 1).first()
    if org is None:
        org = Organisation(o_id=1, name="Test Org")
        session.add(org)
        session.commit()
    return org


def _create_rule_user(session, *, email: str, role_name: str, grant_promote: bool) -> User:
    org = _ensure_org(session)
    hashed_password = bcrypt.hashpw("rulepass".encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    role = session.query(Role).filter(Role.name == role_name, Role.o_id == int(org.o_id)).first()
    if role is None:
        role = Role(name=role_name, description="Can manage rules", o_id=int(org.o_id))
        session.add(role)
        session.commit()

    user = session.query(User).filter(User.email == email).first()
    if user is None:
        user = User(
            email=email,
            password=hashed_password,
            active=True,
            fs_uniquifier=email,
            o_id=int(org.o_id),
        )
        user.roles.append(role)
        session.add(user)
        session.commit()

    PermissionManager.db_session = session
    PermissionManager.init_default_actions()
    PermissionManager.grant_permission(role.id, PermissionAction.VIEW_RULES)
    PermissionManager.grant_permission(role.id, PermissionAction.MODIFY_RULE)
    if grant_promote:
        PermissionManager.grant_permission(role.id, PermissionAction.PROMOTE_RULES)

    return user


def _create_client(session, *, email: str, role_name: str, grant_promote: bool):
    user = _create_rule_user(session, email=email, role_name=role_name, grant_promote=grant_promote)
    token = create_access_token(
        user_id=int(user.id),
        email=str(user.email),
        roles=[role.name for role in user.roles],
        org_id=int(user.o_id),
    )

    with TestClient(app) as client:
        client.test_data = {
            "token": token,
            "session": session,
            "user": user,
            "org": _ensure_org(session),
        }  # type: ignore[attr-defined]
        yield client


@pytest.fixture(scope="function")
def auto_promote_rule_client(session):
    yield from _create_client(
        session,
        email="auto-promote-rule@example.com",
        role_name="auto_promote_rule_manager",
        grant_promote=True,
    )


@pytest.fixture(scope="function")
def modify_only_rule_client(session):
    yield from _create_client(
        session,
        email="modify-only-rule@example.com",
        role_name="modify_only_rule_manager",
        grant_promote=False,
    )


def _set_auto_promote_setting(session, org_id: int, enabled: bool) -> None:
    setting = (
        session.query(RuntimeSetting)
        .filter(
            RuntimeSetting.key == "auto_promote_active_rule_updates",
            RuntimeSetting.o_id == org_id,
        )
        .first()
    )
    if setting is None:
        setting = RuntimeSetting(
            key="auto_promote_active_rule_updates",
            o_id=org_id,
            value_type="bool",
            value="true" if enabled else "false",
        )
        session.add(setting)
    else:
        setting.value_type = "bool"
        setting.value = "true" if enabled else "false"
    session.commit()


def _create_active_rule(session, org_id: int, *, rid: str) -> RuleModel:
    rule = RuleModel(
        rid=rid,
        logic="event.amount > 100",
        description="Original active rule",
        o_id=org_id,
        status=RuleStatus.ACTIVE,
        effective_from=datetime.now(UTC),
    )
    session.add(rule)
    session.commit()
    return rule


def _save_production_config(session, org_id: int) -> None:
    producer = RDBRuleEngineConfigProducer(db=session, o_id=org_id)
    producer.save_config(RDBRuleManager(db=session, o_id=org_id), changed_by="test")


def test_update_active_rule_keeps_current_default_draft_flow(auto_promote_rule_client):
    token = auto_promote_rule_client.test_data["token"]
    session = auto_promote_rule_client.test_data["session"]
    org = auto_promote_rule_client.test_data["org"]

    rule = _create_active_rule(session, int(org.o_id), rid="active_rule_default_draft")
    _save_production_config(session, int(org.o_id))

    response = auto_promote_rule_client.put(
        f"/api/v2/rules/{rule.r_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"description": "Updated into draft"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["message"] == "Rule updated in draft status. Promote to activate."
    assert payload["rule"]["status"] == "draft"
    assert payload["rule"]["approved_by"] is None
    assert payload["rule"]["approved_at"] is None

    session.refresh(rule)
    assert rule.status == RuleStatus.DRAFT

    production_config = session.query(RuleEngineConfig).filter(RuleEngineConfig.label == "production").one()
    assert production_config.config == []


def test_update_active_rule_auto_promotes_when_setting_enabled(auto_promote_rule_client):
    token = auto_promote_rule_client.test_data["token"]
    session = auto_promote_rule_client.test_data["session"]
    org = auto_promote_rule_client.test_data["org"]
    user = auto_promote_rule_client.test_data["user"]

    _set_auto_promote_setting(session, int(org.o_id), True)
    rule = _create_active_rule(session, int(org.o_id), rid="active_rule_auto_promote")
    _save_production_config(session, int(org.o_id))

    response = auto_promote_rule_client.put(
        f"/api/v2/rules/{rule.r_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "description": "Updated and still active",
            "logic": "event.amount > 250",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["message"] == "Rule updated and kept active."
    assert payload["rule"]["status"] == "active"
    assert payload["rule"]["logic"] == "event.amount > 250"
    assert payload["rule"]["description"] == "Updated and still active"
    assert payload["rule"]["approved_by"] == int(user.id)
    assert payload["rule"]["approved_at"] is not None
    assert payload["rule"]["effective_from"] is not None

    session.refresh(rule)
    assert rule.status == RuleStatus.ACTIVE
    assert rule.approved_by == user.id
    assert rule.approved_at is not None
    assert rule.effective_from is not None

    production_config = session.query(RuleEngineConfig).filter(RuleEngineConfig.label == "production").one()
    assert len(production_config.config) == 1
    assert production_config.config[0]["description"] == "Updated and still active"
    assert production_config.config[0]["logic"] == "event.amount > 250"
    assert production_config.config[0]["rid"] == "active_rule_auto_promote"
    assert production_config.config[0]["r_id"] == rule.r_id

    history = (
        session.query(RuleHistory).filter(RuleHistory.r_id == rule.r_id).order_by(RuleHistory.version.desc()).first()
    )
    assert history is not None
    assert history.action == "updated"
    assert history.status == RuleStatus.ACTIVE
    assert history.to_status == RuleStatus.ACTIVE
    assert history.approved_by == user.id
    assert history.approved_at is not None


def test_update_active_rule_auto_promote_requires_promote_permission(modify_only_rule_client):
    token = modify_only_rule_client.test_data["token"]
    session = modify_only_rule_client.test_data["session"]
    org = modify_only_rule_client.test_data["org"]

    _set_auto_promote_setting(session, int(org.o_id), True)
    rule = _create_active_rule(session, int(org.o_id), rid="active_rule_requires_promote")
    _save_production_config(session, int(org.o_id))

    response = modify_only_rule_client.put(
        f"/api/v2/rules/{rule.r_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"description": "Attempt forbidden live edit"},
    )

    assert response.status_code == 403
    assert (
        response.json()["detail"]
        == "PROMOTE_RULES permission is required to update active rules when auto-promotion is enabled"
    )

    session.refresh(rule)
    assert rule.description == "Original active rule"
    assert rule.status == RuleStatus.ACTIVE

    production_config = session.query(RuleEngineConfig).filter(RuleEngineConfig.label == "production").one()
    assert len(production_config.config) == 1
    assert production_config.config[0]["description"] == "Original active rule"
    assert production_config.config[0]["logic"] == "event.amount > 100"
    assert production_config.config[0]["rid"] == "active_rule_requires_promote"
    assert production_config.config[0]["r_id"] == rule.r_id

    history = session.query(RuleHistory).filter(RuleHistory.r_id == rule.r_id).all()
    assert history == []


def test_update_draft_rule_stays_draft_even_when_auto_promote_enabled(auto_promote_rule_client):
    token = auto_promote_rule_client.test_data["token"]
    session = auto_promote_rule_client.test_data["session"]
    org = auto_promote_rule_client.test_data["org"]

    _set_auto_promote_setting(session, int(org.o_id), True)
    draft_rule = RuleModel(
        rid="draft_rule_stays_draft",
        logic="event.amount > 42",
        description="Draft rule",
        o_id=int(org.o_id),
        status=RuleStatus.DRAFT,
    )
    session.add(draft_rule)
    session.commit()

    response = auto_promote_rule_client.put(
        f"/api/v2/rules/{draft_rule.r_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"description": "Draft edit"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["message"] == "Rule updated in draft status. Promote to activate."
    assert payload["rule"]["status"] == "draft"
    assert payload["rule"]["approved_by"] is None
    assert payload["rule"]["approved_at"] is None
