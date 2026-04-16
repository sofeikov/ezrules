import bcrypt
import time

import pytest
from fastapi.testclient import TestClient

from ezrules.backend.api_v2.auth.jwt import create_access_token
from ezrules.backend.api_v2.main import app
from ezrules.backend.tasks import app as celery_app
from ezrules.backend.tasks import backtest_rule_change
from ezrules.core.permissions import PermissionManager
from ezrules.core.permissions_constants import PermissionAction
from ezrules.models.backend_core import FieldTypeConfig, Organisation, Role, TestingRecordLog, User
from ezrules.models.backend_core import Rule as RuleModel


def _get_or_create_org(session):
    org = session.query(Organisation).filter(Organisation.o_id == 1).first()
    if not org:
        org = Organisation(o_id=1, name="Test Org")
        session.add(org)
        session.commit()
    return org


def _create_rule(session, *, rid: str, logic: str):
    org = _get_or_create_org(session)
    rule = RuleModel(rid=rid, logic=logic, description="Backtest guardrail rule", o_id=org.o_id)
    session.add(rule)
    session.commit()
    return org, rule


def _insert_record(session, *, org_id: int, event_id: str, event: dict):
    session.add(
        TestingRecordLog(
            event=event,
            event_timestamp=1700000000,
            event_id=event_id,
            o_id=org_id,
        )
    )


@pytest.fixture(scope="function")
def backtest_guardrail_client(session):
    original_always_eager = celery_app.conf.task_always_eager
    original_eager_propagates = celery_app.conf.task_eager_propagates
    original_store_eager_result = getattr(celery_app.conf, "task_store_eager_result", False)

    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True
    celery_app.conf.task_store_eager_result = True

    hashed_password = bcrypt.hashpw("guardrailpass".encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    org = _get_or_create_org(session)

    role = session.query(Role).filter(Role.name == "backtest_guardrail_manager").first()
    if not role:
        role = Role(name="backtest_guardrail_manager", description="Can manage backtests")
        session.add(role)
        session.commit()

    user = session.query(User).filter(User.email == "backtest-guardrail@example.com").first()
    if not user:
        user = User(
            email="backtest-guardrail@example.com",
            password=hashed_password,
            active=True,
            fs_uniquifier="backtest-guardrail@example.com",
            o_id=org.o_id,
        )
        user.roles.append(role)
        session.add(user)
        session.commit()

    PermissionManager.db_session = session
    PermissionManager.init_default_actions()
    PermissionManager.grant_permission(role.id, PermissionAction.VIEW_RULES)
    PermissionManager.grant_permission(role.id, PermissionAction.MODIFY_RULE)

    token = create_access_token(user_id=int(user.id), email=str(user.email), roles=[role.name], org_id=int(user.o_id))

    with TestClient(app) as client:
        client.test_data = {"token": token, "session": session, "org": org}  # type: ignore[attr-defined]
        yield client

    celery_app.conf.task_always_eager = original_always_eager
    celery_app.conf.task_eager_propagates = original_eager_propagates
    celery_app.conf.task_store_eager_result = original_store_eager_result


class TestBacktestingGuardrails:
    def test_backtest_applies_field_casting_before_comparison(self, session):
        org, rule = _create_rule(
            session,
            rid="BT_GUARD_001",
            logic="if $amount > 100:\n\treturn !HOLD",
        )
        session.add(FieldTypeConfig(field_name="amount", configured_type="integer", o_id=org.o_id))
        _insert_record(session, org_id=org.o_id, event_id="cast-1", event={"amount": "150"})
        _insert_record(session, org_id=org.o_id, event_id="cast-2", event={"amount": "50"})
        session.commit()

        result = backtest_rule_change(rule.r_id, "if $amount > 120:\n\treturn !BLOCK", int(org.o_id))

        assert "error" not in result
        assert result["total_records"] == 2
        assert result["eligible_records"] == 2
        assert result["skipped_records"] == 0
        assert result["stored_result"]["HOLD"] == 1
        assert result["proposed_result"]["BLOCK"] == 1
        assert result["warnings"] == []

    def test_backtest_uses_common_eligible_subset_for_new_fields(self, session):
        org, rule = _create_rule(
            session,
            rid="BT_GUARD_002",
            logic="if $amount > 100:\n\treturn !HOLD",
        )
        _insert_record(session, org_id=org.o_id, event_id="subset-1", event={"amount": 150, "country": "US"})
        _insert_record(session, org_id=org.o_id, event_id="subset-2", event={"amount": 150})
        _insert_record(session, org_id=org.o_id, event_id="subset-3", event={"amount": 50, "country": "US"})
        session.commit()

        result = backtest_rule_change(
            rule.r_id,
            'if $amount > 100 and $country == "US":\n\treturn !BLOCK',
            int(org.o_id),
        )

        assert "error" not in result
        assert result["total_records"] == 2
        assert result["eligible_records"] == 2
        assert result["skipped_records"] == 1
        assert result["stored_result"]["HOLD"] == 1
        assert result["proposed_result"]["BLOCK"] == 1
        assert any("country" in warning for warning in result["warnings"])

    def test_backtest_skips_records_rejected_by_required_field_contracts(self, session):
        org, rule = _create_rule(
            session,
            rid="BT_GUARD_003",
            logic="if $amount > 100:\n\treturn !HOLD",
        )
        session.add(FieldTypeConfig(field_name="merchant_id", configured_type="string", required=True, o_id=org.o_id))
        _insert_record(session, org_id=org.o_id, event_id="required-1", event={"amount": 150})
        _insert_record(session, org_id=org.o_id, event_id="required-2", event={"amount": 200, "merchant_id": "m-1"})
        session.commit()

        result = backtest_rule_change(rule.r_id, "if $amount > 120:\n\treturn !BLOCK", int(org.o_id))

        assert "error" not in result
        assert result["total_records"] == 1
        assert result["eligible_records"] == 1
        assert result["skipped_records"] == 1
        assert any("merchant_id" in warning for warning in result["warnings"])

    def test_backtest_task_endpoint_exposes_eligibility_counts_and_warnings(self, backtest_guardrail_client, session):
        token = backtest_guardrail_client.test_data["token"]  # type: ignore[attr-defined]
        org, rule = _create_rule(
            session,
            rid="BT_GUARD_004",
            logic="if $amount > 100:\n\treturn !HOLD",
        )
        _insert_record(session, org_id=org.o_id, event_id="api-1", event={"amount": 150, "country": "US"})
        _insert_record(session, org_id=org.o_id, event_id="api-2", event={"amount": 200})
        session.commit()

        trigger_response = backtest_guardrail_client.post(
            "/api/v2/backtesting",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "r_id": rule.r_id,
                "new_rule_logic": 'if $amount > 100 and $country == "US":\n\treturn !BLOCK',
            },
        )

        assert trigger_response.status_code == 200
        task_id = trigger_response.json()["task_id"]

        data = None
        for _ in range(10):
            task_response = backtest_guardrail_client.get(
                f"/api/v2/backtesting/task/{task_id}",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert task_response.status_code == 200
            data = task_response.json()
            if data["status"] != "PENDING":
                break
            time.sleep(0.1)

        assert data is not None
        assert data["status"] == "SUCCESS"
        assert data["eligible_records"] == 1
        assert data["skipped_records"] == 1
        assert any("country" in warning for warning in data["warnings"])
