# ruff: noqa: F811

import pytest

from ezrules.backend import agent_tools
from ezrules.backend.api_v2.routes import agent_tools as agent_tools_routes
from ezrules.backend.api_v2.routes import backtesting as backtesting_routes
from ezrules.backend.tasks import execute_backtest_rule_change
from ezrules.models.backend_core import RuleBackTestingResult
from tests.test_api_v2_agent_tools import (  # noqa: F401
    agent_tools_client,
    agent_tools_fixture,
)
from tests.test_backtesting import (  # noqa: F401
    backtesting_test_client,
    sample_rule_for_bt,
)

INVALID_PREDICATE_RETURN = "return $amount > 100"


def test_backtest_route_rejects_predicate_return_before_queueing(
    backtesting_test_client,
    sample_rule_for_bt,
    monkeypatch,
) -> None:
    session = backtesting_test_client.test_data["session"]
    token = backtesting_test_client.test_data["token"]
    result_count = session.query(RuleBackTestingResult).count()

    def fail_if_queued(*args, **kwargs):
        raise AssertionError("invalid proposal reached the backtest queue")

    monkeypatch.setattr(backtesting_routes, "_enqueue_backtest", fail_if_queued)

    response = backtesting_test_client.post(
        "/api/v2/backtesting",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "r_id": sample_rule_for_bt.r_id,
            "new_rule_logic": INVALID_PREDICATE_RETURN,
        },
    )

    assert response.status_code == 400
    assert "direct configured outcome" in response.json()["detail"]
    assert session.query(RuleBackTestingResult).count() == result_count


def test_backtest_worker_rejects_predicate_return_before_metrics(session, sample_rule_for_bt) -> None:
    result = execute_backtest_rule_change(
        int(sample_rule_for_bt.r_id),
        INVALID_PREDICATE_RETURN,
        int(sample_rule_for_bt.o_id),
    )

    assert set(result) == {"error"}
    assert "direct configured outcome" in result["error"]


def test_agent_tool_route_rejects_predicate_return_before_metrics(
    agent_tools_client,
    agent_tools_fixture,
    monkeypatch,
) -> None:
    token = agent_tools_client.test_data["token"]
    rule = agent_tools_fixture["rule"]

    def fail_if_metrics_run(*args, **kwargs):
        raise AssertionError("invalid proposal reached agent-tool metrics")

    monkeypatch.setattr(agent_tools_routes, "build_blast_radius", fail_if_metrics_run)

    response = agent_tools_client.post(
        "/api/v2/agent-tools/rule-blast-radius",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "rule_id": int(rule.r_id),
            "proposed_logic": INVALID_PREDICATE_RETURN,
        },
    )

    assert response.status_code == 400
    assert "direct configured outcome" in response.json()["detail"]


def test_agent_tool_internal_replay_rejects_predicate_return_before_metrics(
    session,
    agent_tools_fixture,
) -> None:
    rule = agent_tools_fixture["rule"]

    with pytest.raises(ValueError, match="direct configured outcome"):
        agent_tools.build_blast_radius(
            session,
            org_id=int(rule.o_id),
            rule_id=int(rule.r_id),
            proposed_logic=INVALID_PREDICATE_RETURN,
            lookback_days=30,
            group_by=[],
            sample_limit=10,
            max_records=100,
        )
