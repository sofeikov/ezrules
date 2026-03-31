import bcrypt
import pytest
from fastapi.testclient import TestClient

from ezrules.backend.api_v2.auth.jwt import create_access_token
from ezrules.backend.api_v2.main import app
from ezrules.backend.api_v2.routes import backtesting as backtesting_routes
from ezrules.backend.tasks import app as celery_app
from ezrules.core.permissions import PermissionManager
from ezrules.core.permissions_constants import PermissionAction
from ezrules.models.backend_core import Organisation, Role, RuleBackTestingResult, TestingRecordLog, User
from ezrules.models.backend_core import Rule as RuleModel


def _ensure_org(session) -> Organisation:
    org = session.query(Organisation).filter(Organisation.o_id == 1).first()
    if org is None:
        org = Organisation(o_id=1, name="Backtesting Controls Org")
        session.add(org)
        session.commit()
    return org


@pytest.fixture(scope="function")
def backtesting_controls_client(session):
    original_always_eager = celery_app.conf.task_always_eager
    original_eager_propagates = celery_app.conf.task_eager_propagates

    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True

    hashed_password = bcrypt.hashpw(b"btcontrols", bcrypt.gensalt()).decode("utf-8")
    org = _ensure_org(session)

    role = session.query(Role).filter(Role.name == "bt_controls_manager", Role.o_id == int(org.o_id)).first()
    if role is None:
        role = Role(name="bt_controls_manager", description="Can manage backtesting controls", o_id=int(org.o_id))
        session.add(role)
        session.commit()

    user = session.query(User).filter(User.email == "bt-controls@example.com").first()
    if user is None:
        user = User(
            email="bt-controls@example.com",
            password=hashed_password,
            active=True,
            fs_uniquifier="bt-controls@example.com",
            o_id=int(org.o_id),
        )
        user.roles.append(role)
        session.add(user)
        session.commit()

    PermissionManager.db_session = session
    PermissionManager.init_default_actions()
    PermissionManager.grant_permission(role.id, PermissionAction.VIEW_RULES)
    PermissionManager.grant_permission(role.id, PermissionAction.MODIFY_RULE)

    token = create_access_token(
        user_id=int(user.id),
        email=str(user.email),
        roles=[item.name for item in user.roles],
        org_id=int(user.o_id),
    )

    with TestClient(app) as client:
        client.test_data = {"token": token, "session": session, "org": org}  # type: ignore[attr-defined]
        yield client

    celery_app.conf.task_always_eager = original_always_eager
    celery_app.conf.task_eager_propagates = original_eager_propagates


def _create_rule_with_history(session, *, logic: str = 'if $amount > 100:\n\treturn "HOLD"') -> RuleModel:
    org = _ensure_org(session)
    rule = RuleModel(
        rid=f"BT_CTRL_{session.query(RuleModel).count() + 1}",
        logic=logic,
        description="Backtesting controls rule",
        o_id=int(org.o_id),
    )
    session.add(rule)
    session.commit()

    session.add_all(
        [
            TestingRecordLog(
                event={"amount": 150},
                event_timestamp=1_800_000,
                event_id=f"bt-controls-{rule.r_id}-1",
                o_id=int(org.o_id),
            ),
            TestingRecordLog(
                event={"amount": 50},
                event_timestamp=1_800_001,
                event_id=f"bt-controls-{rule.r_id}-2",
                o_id=int(org.o_id),
            ),
        ]
    )
    session.commit()
    return rule


def test_trigger_backtest_persists_result_metrics(backtesting_controls_client, monkeypatch):
    session = backtesting_controls_client.test_data["session"]  # type: ignore[attr-defined]
    token = backtesting_controls_client.test_data["token"]  # type: ignore[attr-defined]
    rule = _create_rule_with_history(session)

    def fail_async_result(*args, **kwargs):  # noqa: ARG001
        raise AssertionError("Expected persisted result_metrics to satisfy task result reads")

    monkeypatch.setattr(backtesting_routes, "AsyncResult", fail_async_result)

    response = backtesting_controls_client.post(
        "/api/v2/backtesting",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "r_id": int(rule.r_id),
            "new_rule_logic": 'if $amount > 40:\n\treturn "BLOCK"',
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["queue_status"] == "pending"

    stored = session.query(RuleBackTestingResult).filter(RuleBackTestingResult.task_id == payload["task_id"]).one()
    assert stored.status == "done"
    assert stored.completed_at is not None
    assert stored.result_metrics is not None
    assert stored.result_metrics["total_records"] == 2
    assert stored.result_metrics["stored_result"] == {"HOLD": 1}
    assert stored.result_metrics["proposed_result"] == {"BLOCK": 2}

    task_response = backtesting_controls_client.get(
        f"/api/v2/backtesting/task/{payload['task_id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert task_response.status_code == 200
    task_payload = task_response.json()
    assert task_payload["status"] == "SUCCESS"
    assert task_payload["queue_status"] == "done"
    assert task_payload["total_records"] == 2
    assert task_payload["completed_at"] is not None


def test_cancel_backtest_marks_job_cancelled_and_revokes(backtesting_controls_client, monkeypatch):
    session = backtesting_controls_client.test_data["session"]  # type: ignore[attr-defined]
    token = backtesting_controls_client.test_data["token"]  # type: ignore[attr-defined]
    rule = _create_rule_with_history(session)

    record = RuleBackTestingResult(
        r_id=int(rule.r_id),
        task_id="cancel-me",
        stored_logic=rule.logic,
        proposed_logic='if $amount > 200:\n\treturn "BLOCK"',
        status="running",
    )
    session.add(record)
    session.commit()

    class FakeAsyncResult:
        state = "STARTED"
        result = None

        def __init__(self, task_id, app):  # noqa: ARG002
            pass

    revoke_calls: list[tuple[str, bool]] = []

    def fake_revoke(task_id: str, terminate: bool = False):
        revoke_calls.append((task_id, terminate))

    monkeypatch.setattr(backtesting_routes, "AsyncResult", FakeAsyncResult)
    monkeypatch.setattr(celery_app.control, "revoke", fake_revoke)

    response = backtesting_controls_client.delete(
        "/api/v2/backtesting/cancel-me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["queue_status"] == "cancelled"
    assert revoke_calls == [("cancel-me", True)]

    session.refresh(record)
    assert record.status == "cancelled"
    assert record.completed_at is not None
    assert record.result_metrics == {"error": "Backtest cancelled by operator"}

    task_response = backtesting_controls_client.get(
        "/api/v2/backtesting/task/cancel-me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert task_response.status_code == 200
    task_payload = task_response.json()
    assert task_payload["status"] == "CANCELLED"
    assert task_payload["queue_status"] == "cancelled"
    assert "cancelled" in task_payload["error"].lower()


def test_retry_backtest_requeues_failed_snapshot(backtesting_controls_client):
    session = backtesting_controls_client.test_data["session"]  # type: ignore[attr-defined]
    token = backtesting_controls_client.test_data["token"]  # type: ignore[attr-defined]
    rule = _create_rule_with_history(session)

    failed_record = RuleBackTestingResult(
        r_id=int(rule.r_id),
        task_id="failed-task",
        stored_logic=rule.logic,
        proposed_logic='if $amount > 40:\n\treturn "BLOCK"',
        status="failed",
        result_metrics={"error": "worker crashed"},
    )
    session.add(failed_record)
    session.commit()

    rule.logic = 'if $amount > 1000:\n\treturn "IGNORE"'
    session.commit()

    response = backtesting_controls_client.post(
        "/api/v2/backtesting/failed-task/retry",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["queue_status"] == "pending"
    assert payload["task_id"] != "failed-task"

    retried = session.query(RuleBackTestingResult).filter(RuleBackTestingResult.task_id == payload["task_id"]).one()
    assert retried.bt_id != failed_record.bt_id
    assert retried.status == "done"
    assert retried.stored_logic == failed_record.stored_logic
    assert retried.proposed_logic == failed_record.proposed_logic
    assert retried.result_metrics is not None
    assert retried.result_metrics["stored_result"] == {"HOLD": 1}
    assert retried.result_metrics["proposed_result"] == {"BLOCK": 2}

    session.refresh(failed_record)
    assert failed_record.status == "failed"
    assert failed_record.result_metrics == {"error": "worker crashed"}
