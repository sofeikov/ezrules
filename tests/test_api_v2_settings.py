"""Tests for FastAPI v2 runtime settings endpoints."""

import bcrypt
import pytest
from fastapi.testclient import TestClient

from ezrules.backend.api_v2.auth.jwt import create_access_token
from ezrules.backend.api_v2.main import app
from ezrules.core.permissions import PermissionManager
from ezrules.core.permissions_constants import PermissionAction
from ezrules.models.backend_core import (
    AllowedOutcome,
    Label,
    Organisation,
    OutcomeHistory,
    Role,
    RuleQualityPair,
    RuntimeSetting,
    User,
)
from ezrules.settings import app_settings


def _ensure_org(session) -> None:
    org = session.query(Organisation).filter(Organisation.o_id == app_settings.ORG_ID).first()
    if org is None:
        session.add(Organisation(o_id=app_settings.ORG_ID, name="Test Org"))
        session.commit()


@pytest.fixture(scope="function")
def settings_test_client(session):
    """Create a test client with a settings-admin user."""
    hashed_password = bcrypt.hashpw("settingspass".encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    role = session.query(Role).filter(Role.name == "settings_admin").first()
    if not role:
        role = Role(name="settings_admin", description="Can view and manage runtime settings")
        session.add(role)
        session.commit()

    user = session.query(User).filter(User.email == "settings_admin@example.com").first()
    if not user:
        user = User(
            email="settings_admin@example.com",
            password=hashed_password,
            active=True,
            fs_uniquifier="settings_admin@example.com",
        )
        user.roles.append(role)
        session.add(user)
        session.commit()

    PermissionManager.db_session = session
    PermissionManager.init_default_actions()
    PermissionManager.grant_permission(role.id, PermissionAction.VIEW_ROLES)
    PermissionManager.grant_permission(role.id, PermissionAction.MANAGE_PERMISSIONS)

    token = create_access_token(
        user_id=int(user.id),
        email=str(user.email),
        roles=[role.name],
    )

    with TestClient(app) as client:
        client.test_data = {
            "token": token,
            "session": session,
            "user": user,
            "role": role,
        }  # type: ignore[attr-defined]
        yield client


class TestRuntimeSettings:
    def test_get_runtime_settings_defaults(self, settings_test_client):
        token = settings_test_client.test_data["token"]

        response = settings_test_client.get(
            "/api/v2/settings/runtime",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["rule_quality_lookback_days"] == app_settings.RULE_QUALITY_LOOKBACK_DAYS
        assert data["default_rule_quality_lookback_days"] == app_settings.RULE_QUALITY_LOOKBACK_DAYS

    def test_update_runtime_settings(self, settings_test_client):
        token = settings_test_client.test_data["token"]
        session = settings_test_client.test_data["session"]

        update_response = settings_test_client.put(
            "/api/v2/settings/runtime",
            headers={"Authorization": f"Bearer {token}"},
            json={"rule_quality_lookback_days": 21},
        )
        assert update_response.status_code == 200
        assert update_response.json()["rule_quality_lookback_days"] == 21

        get_response = settings_test_client.get(
            "/api/v2/settings/runtime",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert get_response.status_code == 200
        assert get_response.json()["rule_quality_lookback_days"] == 21

        stored = session.query(RuntimeSetting).filter(RuntimeSetting.key == "rule_quality_lookback_days").first()
        assert stored is not None
        assert stored.value_type == "int"
        assert stored.value == "21"

    def test_get_runtime_settings_unauthorized(self, settings_test_client):
        response = settings_test_client.get("/api/v2/settings/runtime")
        assert response.status_code == 401

    def test_update_runtime_settings_without_manage_permission(self, session):
        hashed_password = bcrypt.hashpw("settingsreadpass".encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

        role = Role(name="settings_read_only", description="Can only view settings")
        session.add(role)
        session.commit()

        user = User(
            email="settings_read_only@example.com",
            password=hashed_password,
            active=True,
            fs_uniquifier="settings_read_only@example.com",
        )
        user.roles.append(role)
        session.add(user)
        session.commit()

        PermissionManager.db_session = session
        PermissionManager.init_default_actions()
        PermissionManager.grant_permission(role.id, PermissionAction.VIEW_ROLES)

        token = create_access_token(
            user_id=int(user.id),
            email=str(user.email),
            roles=[role.name],
        )

        with TestClient(app) as client:
            response = client.put(
                "/api/v2/settings/runtime",
                headers={"Authorization": f"Bearer {token}"},
                json={"rule_quality_lookback_days": 10},
            )

            assert response.status_code == 403


class TestOutcomeHierarchySettings:
    def test_list_outcome_hierarchy(self, settings_test_client):
        token = settings_test_client.test_data["token"]
        session = settings_test_client.test_data["session"]

        _ensure_org(session)
        session.add_all(
            [
                AllowedOutcome(outcome_name="CANCEL", severity_rank=1, o_id=app_settings.ORG_ID),
                AllowedOutcome(outcome_name="HOLD", severity_rank=2, o_id=app_settings.ORG_ID),
                AllowedOutcome(outcome_name="RELEASE", severity_rank=3, o_id=app_settings.ORG_ID),
            ]
        )
        session.commit()

        response = settings_test_client.get(
            "/api/v2/settings/outcome-hierarchy",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        payload = response.json()
        assert [item["outcome_name"] for item in payload["outcomes"]] == ["CANCEL", "HOLD", "RELEASE"]
        assert [item["severity_rank"] for item in payload["outcomes"]] == [1, 2, 3]

    def test_update_outcome_hierarchy_reorders_outcomes(self, settings_test_client):
        token = settings_test_client.test_data["token"]
        session = settings_test_client.test_data["session"]
        user = settings_test_client.test_data["user"]

        _ensure_org(session)
        outcomes = [
            AllowedOutcome(outcome_name="CANCEL", severity_rank=1, o_id=app_settings.ORG_ID),
            AllowedOutcome(outcome_name="HOLD", severity_rank=2, o_id=app_settings.ORG_ID),
            AllowedOutcome(outcome_name="RELEASE", severity_rank=3, o_id=app_settings.ORG_ID),
        ]
        session.add_all(outcomes)
        session.commit()

        response = settings_test_client.put(
            "/api/v2/settings/outcome-hierarchy",
            headers={"Authorization": f"Bearer {token}"},
            json={"ordered_ao_ids": [outcomes[2].ao_id, outcomes[1].ao_id, outcomes[0].ao_id]},
        )

        assert response.status_code == 200
        payload = response.json()
        assert [item["outcome_name"] for item in payload["outcomes"]] == ["RELEASE", "HOLD", "CANCEL"]

        session.expire_all()
        stored = (
            session.query(AllowedOutcome)
            .filter(AllowedOutcome.o_id == app_settings.ORG_ID)
            .order_by(AllowedOutcome.severity_rank.asc())
            .all()
        )
        assert [item.outcome_name for item in stored] == ["RELEASE", "HOLD", "CANCEL"]
        assert [item.severity_rank for item in stored] == [1, 2, 3]

        history = (
            session.query(OutcomeHistory)
            .filter(OutcomeHistory.action == "reordered")
            .order_by(OutcomeHistory.id.asc())
            .all()
        )
        assert len(history) == 2
        assert {item.outcome_name for item in history} == {"RELEASE", "CANCEL"}
        assert {item.changed_by for item in history} == {str(user.email)}

    def test_update_outcome_hierarchy_requires_full_set(self, settings_test_client):
        token = settings_test_client.test_data["token"]
        session = settings_test_client.test_data["session"]

        _ensure_org(session)
        outcomes = [
            AllowedOutcome(outcome_name="CANCEL", severity_rank=1, o_id=app_settings.ORG_ID),
            AllowedOutcome(outcome_name="HOLD", severity_rank=2, o_id=app_settings.ORG_ID),
        ]
        session.add_all(outcomes)
        session.commit()

        response = settings_test_client.put(
            "/api/v2/settings/outcome-hierarchy",
            headers={"Authorization": f"Bearer {token}"},
            json={"ordered_ao_ids": [outcomes[0].ao_id]},
        )

        assert response.status_code == 400


class TestRuleQualityPairsSettings:
    def test_list_rule_quality_pairs_empty(self, settings_test_client):
        token = settings_test_client.test_data["token"]
        response = settings_test_client.get(
            "/api/v2/settings/rule-quality-pairs",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        assert response.json()["pairs"] == []

    def test_create_update_delete_rule_quality_pair(self, settings_test_client):
        token = settings_test_client.test_data["token"]
        session = settings_test_client.test_data["session"]

        _ensure_org(session)

        outcome = AllowedOutcome(
            outcome_name="SETTINGS_OUTCOME",
            severity_rank=10,
            o_id=app_settings.ORG_ID,
        )
        label = Label(label="SETTINGS_LABEL")
        session.add_all([outcome, label])
        session.commit()

        create_response = settings_test_client.post(
            "/api/v2/settings/rule-quality-pairs",
            headers={"Authorization": f"Bearer {token}"},
            json={"outcome": "SETTINGS_OUTCOME", "label": "SETTINGS_LABEL"},
        )
        assert create_response.status_code == 200
        created = create_response.json()
        assert created["outcome"] == "SETTINGS_OUTCOME"
        assert created["label"] == "SETTINGS_LABEL"
        assert created["active"] is True

        pair_id = created["rqp_id"]
        update_response = settings_test_client.put(
            f"/api/v2/settings/rule-quality-pairs/{pair_id}",
            headers={"Authorization": f"Bearer {token}"},
            json={"active": False},
        )
        assert update_response.status_code == 200
        assert update_response.json()["active"] is False

        list_response = settings_test_client.get(
            "/api/v2/settings/rule-quality-pairs",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert list_response.status_code == 200
        assert len(list_response.json()["pairs"]) == 1
        assert list_response.json()["pairs"][0]["active"] is False

        delete_response = settings_test_client.delete(
            f"/api/v2/settings/rule-quality-pairs/{pair_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert delete_response.status_code == 204
        assert session.query(RuleQualityPair).count() == 0

    def test_rule_quality_pair_options(self, settings_test_client):
        token = settings_test_client.test_data["token"]
        session = settings_test_client.test_data["session"]

        _ensure_org(session)
        outcome = AllowedOutcome(
            outcome_name="SETTINGS_OUTCOME_OPTIONS",
            severity_rank=11,
            o_id=app_settings.ORG_ID,
        )
        label = Label(label="SETTINGS_LABEL_OPTIONS")
        session.add_all([outcome, label])
        session.commit()

        response = settings_test_client.get(
            "/api/v2/settings/rule-quality-pairs/options",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        payload = response.json()
        assert "SETTINGS_OUTCOME_OPTIONS" in payload["outcomes"]
        assert "SETTINGS_LABEL_OPTIONS" in payload["labels"]

    def test_create_rule_quality_pair_duplicate_returns_conflict(self, settings_test_client):
        token = settings_test_client.test_data["token"]
        session = settings_test_client.test_data["session"]

        _ensure_org(session)
        outcome = AllowedOutcome(
            outcome_name="SETTINGS_OUTCOME_DUP",
            severity_rank=12,
            o_id=app_settings.ORG_ID,
        )
        label = Label(label="SETTINGS_LABEL_DUP")
        session.add_all([outcome, label])
        session.commit()

        first = settings_test_client.post(
            "/api/v2/settings/rule-quality-pairs",
            headers={"Authorization": f"Bearer {token}"},
            json={"outcome": "SETTINGS_OUTCOME_DUP", "label": "SETTINGS_LABEL_DUP"},
        )
        assert first.status_code == 200

        duplicate = settings_test_client.post(
            "/api/v2/settings/rule-quality-pairs",
            headers={"Authorization": f"Bearer {token}"},
            json={"outcome": "SETTINGS_OUTCOME_DUP", "label": "SETTINGS_LABEL_DUP"},
        )
        assert duplicate.status_code == 409

    def test_list_rule_quality_pairs_requires_view_roles_permission(self, session):
        hashed_password = bcrypt.hashpw("pairsreadonlypass".encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        role = Role(name="pairs_no_view", description="No view role permission")
        session.add(role)
        session.commit()

        user = User(
            email="pairs_no_view@example.com",
            password=hashed_password,
            active=True,
            fs_uniquifier="pairs_no_view@example.com",
        )
        user.roles.append(role)
        session.add(user)
        session.commit()

        PermissionManager.db_session = session
        PermissionManager.init_default_actions()

        token = create_access_token(
            user_id=int(user.id),
            email=str(user.email),
            roles=[role.name],
        )

        with TestClient(app) as client:
            response = client.get(
                "/api/v2/settings/rule-quality-pairs",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert response.status_code == 403

    def test_mutate_rule_quality_pairs_requires_manage_permissions(self, session):
        hashed_password = bcrypt.hashpw("pairsviewonlypass".encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        role = Role(name="pairs_view_only", description="Can view settings only")
        session.add(role)
        session.commit()

        user = User(
            email="pairs_view_only@example.com",
            password=hashed_password,
            active=True,
            fs_uniquifier="pairs_view_only@example.com",
        )
        user.roles.append(role)
        session.add(user)
        session.commit()

        PermissionManager.db_session = session
        PermissionManager.init_default_actions()
        PermissionManager.grant_permission(role.id, PermissionAction.VIEW_ROLES)

        _ensure_org(session)
        outcome = AllowedOutcome(
            outcome_name="SETTINGS_OUTCOME_PERM",
            severity_rank=13,
            o_id=app_settings.ORG_ID,
        )
        label = Label(label="SETTINGS_LABEL_PERM")
        session.add_all([outcome, label])
        session.commit()

        token = create_access_token(
            user_id=int(user.id),
            email=str(user.email),
            roles=[role.name],
        )

        with TestClient(app) as client:
            response = client.post(
                "/api/v2/settings/rule-quality-pairs",
                headers={"Authorization": f"Bearer {token}"},
                json={"outcome": "SETTINGS_OUTCOME_PERM", "label": "SETTINGS_LABEL_PERM"},
            )
            assert response.status_code == 403
