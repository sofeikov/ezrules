from types import SimpleNamespace

import pytest

from ezrules.backend.api_v2.routes import backtesting as backtesting_routes
from ezrules.models.backend_core import RuleBackTestingResult
from tests.test_backtesting_controls import (
    _create_rule_with_history,
    backtesting_controls_client,  # noqa: F401
)


@pytest.fixture
def controls_client(request):
    return request.getfixturevalue("backtesting_controls_client")


def test_trigger_backtest_uses_legacy_three_arg_task_signature(controls_client, monkeypatch):
    session = controls_client.test_data["session"]  # type: ignore[attr-defined]
    token = controls_client.test_data["token"]  # type: ignore[attr-defined]
    org = controls_client.test_data["org"]  # type: ignore[attr-defined]
    rule = _create_rule_with_history(session)
    queued: dict[str, object] = {}

    def fake_apply_async(*, args, task_id):
        queued["args"] = args
        queued["task_id"] = task_id
        return SimpleNamespace(id=task_id, result=None)

    monkeypatch.setattr(backtesting_routes.backtest_rule_change, "apply_async", fake_apply_async)

    response = controls_client.post(
        "/api/v2/backtesting",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "r_id": int(rule.r_id),
            "new_rule_logic": 'if $amount > 40:\n\treturn "BLOCK"',
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert queued["args"] == [
        int(rule.r_id),
        'if $amount > 40:\n\treturn "BLOCK"',
        int(org.o_id),
    ]
    assert queued["task_id"] == payload["task_id"]


def test_retry_backtest_uses_legacy_three_arg_task_signature(controls_client, monkeypatch):
    session = controls_client.test_data["session"]  # type: ignore[attr-defined]
    token = controls_client.test_data["token"]  # type: ignore[attr-defined]
    org = controls_client.test_data["org"]  # type: ignore[attr-defined]
    rule = _create_rule_with_history(session)
    queued: dict[str, object] = {}

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

    def fake_apply_async(*, args, task_id):
        queued["args"] = args
        queued["task_id"] = task_id
        return SimpleNamespace(id=task_id, result=None)

    monkeypatch.setattr(backtesting_routes.backtest_rule_change, "apply_async", fake_apply_async)

    response = controls_client.post(
        "/api/v2/backtesting/failed-task/retry",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert queued["args"] == [
        int(rule.r_id),
        'if $amount > 40:\n\treturn "BLOCK"',
        int(org.o_id),
    ]
    assert queued["task_id"] == payload["task_id"]
