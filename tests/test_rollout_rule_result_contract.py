# ruff: noqa: F811

import pytest

from ezrules.backend.api_v2.routes.evaluator import _evaluate_rollout_result
from ezrules.backend.rule_executors.executors import LocalRuleExecutorSQL
from ezrules.core.rule_engine import InvalidRuleResultError
from ezrules.core.rule_updater import (
    ROLLOUT_CONFIG_LABEL,
    RDBRuleEngineConfigProducer,
    RDBRuleManager,
    deploy_rule_to_rollout,
    list_candidate_deployments,
)
from ezrules.core.user_lists import PersistentUserListManager
from ezrules.models.backend_core import RuleEngineConfig
from tests.test_api_v2_rollouts import (  # noqa: F401
    active_rollout_rule,
    rollout_test_client,
)


def _evaluate_direct_rollout(session, active_rule, *, candidate_logic: str) -> tuple[dict, list[dict]]:
    deploy_rule_to_rollout(
        db=session,
        o_id=int(active_rule.o_id),
        rule_model=active_rule,
        traffic_percent=100,
        changed_by="contract-test",
        logic_override=candidate_logic,
        description_override="Candidate contract test",
    )
    lre = LocalRuleExecutorSQL(db=session, o_id=int(active_rule.o_id), label="production")
    lre.get_rule_stats()
    result, logs, _metadata = _evaluate_rollout_result(
        event_data={"amount": 200},
        lre=lre,
        rollout_entries=list_candidate_deployments(session, int(active_rule.o_id), ROLLOUT_CONFIG_LABEL),
        assignment_key="always-candidate",
        list_provider=PersistentUserListManager(session, int(active_rule.o_id)),
        stats={},
    )
    return result, logs


def test_rollout_deployment_rejects_predicate_return(
    rollout_test_client,
    active_rollout_rule,
) -> None:
    token = rollout_test_client.test_data["token"]
    session = rollout_test_client.test_data["session"]

    response = rollout_test_client.post(
        f"/api/v2/rules/{active_rollout_rule.r_id}/rollout",
        json={"logic": "return $amount > 100", "traffic_percent": 100},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 400
    assert "direct configured outcome" in response.json()["detail"]
    rollout_config = (
        session.query(RuleEngineConfig)
        .filter(RuleEngineConfig.label == ROLLOUT_CONFIG_LABEL, RuleEngineConfig.o_id == active_rollout_rule.o_id)
        .first()
    )
    assert rollout_config is None or rollout_config.config == []


@pytest.mark.parametrize("candidate_logic", ["return $amount > 100", 'return ""'])
def test_direct_rollout_invalid_candidate_result_falls_back_before_aggregation(
    session,
    rollout_test_client,
    active_rollout_rule,
    candidate_logic,
) -> None:
    result, logs = _evaluate_direct_rollout(session, active_rollout_rule, candidate_logic=candidate_logic)

    assert result["outcome_counters"] == {"CONTROL": 1}
    assert logs[0]["candidate_result"] is None
    assert logs[0]["returned_result"] == "CONTROL"


def test_direct_rollout_invalid_control_result_is_rejected(
    session,
    rollout_test_client,
    active_rollout_rule,
) -> None:
    active_rollout_rule.logic = "return $amount > 100"
    session.commit()
    RDBRuleEngineConfigProducer(db=session, o_id=int(active_rollout_rule.o_id)).save_config(
        RDBRuleManager(db=session, o_id=int(active_rollout_rule.o_id))
    )

    with pytest.raises(InvalidRuleResultError, match="returned bool"):
        _evaluate_direct_rollout(session, active_rollout_rule, candidate_logic="return !CANDIDATE")


def test_direct_rollout_valid_candidate_outcome_is_aggregated(
    session,
    rollout_test_client,
    active_rollout_rule,
) -> None:
    result, logs = _evaluate_direct_rollout(session, active_rollout_rule, candidate_logic="return !CANDIDATE")

    assert result["outcome_counters"] == {"CANDIDATE": 1}
    assert logs[0]["candidate_result"] == "CANDIDATE"
    assert logs[0]["returned_result"] == "CANDIDATE"
