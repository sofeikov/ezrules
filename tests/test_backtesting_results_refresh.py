from datetime import UTC, datetime, timedelta

from ezrules.backend.api_v2.routes import backtesting as backtesting_routes
from ezrules.models.backend_core import RuleBackTestingResult
from tests.test_backtesting_controls import (  # noqa: F401
    _create_rule_with_history,
    backtesting_controls_client,
)


def test_get_backtest_results_refreshes_active_rows(backtesting_controls_client, monkeypatch):  # noqa: F811
    session = backtesting_controls_client.test_data["session"]  # type: ignore[attr-defined]
    token = backtesting_controls_client.test_data["token"]  # type: ignore[attr-defined]
    rule = _create_rule_with_history(session)

    session.add(
        RuleBackTestingResult(
            r_id=int(rule.r_id),
            task_id="refresh-me",
            stored_logic=rule.logic,
            proposed_logic="if $amount > 40:\n\treturn !BLOCK",
            status="pending",
        )
    )
    session.commit()

    class FakeAsyncResult:
        state = "SUCCESS"
        result = {
            "stored_result": {"HOLD": 1},
            "proposed_result": {"BLOCK": 2},
            "total_records": 2,
        }

        def __init__(self, task_id, app):  # noqa: ARG002
            pass

    monkeypatch.setattr(backtesting_routes, "AsyncResult", FakeAsyncResult)

    response = backtesting_controls_client.get(
        f"/api/v2/backtesting/{rule.r_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["results"][0]["task_id"] == "refresh-me"
    assert payload["results"][0]["status"] == "SUCCESS"
    assert payload["results"][0]["queue_status"] == "done"

    stored = session.query(RuleBackTestingResult).filter(RuleBackTestingResult.task_id == "refresh-me").one()
    assert stored.status == "done"
    assert stored.completed_at is not None
    assert stored.result_metrics == {
        "stored_result": {"HOLD": 1},
        "proposed_result": {"BLOCK": 2},
        "total_records": 2,
    }


def test_get_task_result_recovers_orphaned_pending_backtests(backtesting_controls_client, monkeypatch):  # noqa: F811
    session = backtesting_controls_client.test_data["session"]  # type: ignore[attr-defined]
    token = backtesting_controls_client.test_data["token"]  # type: ignore[attr-defined]
    rule = _create_rule_with_history(session)

    record = RuleBackTestingResult(
        r_id=int(rule.r_id),
        task_id="orphaned-task",
        stored_logic=rule.logic,
        proposed_logic="if $amount > 40:\n\treturn !BLOCK",
        status="pending",
        created_at=datetime.now(UTC) - timedelta(seconds=10),
    )
    session.add(record)
    session.commit()

    class FakeAsyncResult:
        state = "PENDING"
        result = None

        def __init__(self, task_id, app):  # noqa: ARG002
            pass

    monkeypatch.setattr(backtesting_routes, "AsyncResult", FakeAsyncResult)

    response = backtesting_controls_client.get(
        "/api/v2/backtesting/task/orphaned-task",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "SUCCESS"
    assert payload["queue_status"] == "done"
    assert payload["total_records"] == 2
    assert payload["stored_result"] == {"HOLD": 1}
    assert payload["proposed_result"] == {"BLOCK": 2}

    session.refresh(record)
    assert record.status == "done"
    assert record.completed_at is not None
