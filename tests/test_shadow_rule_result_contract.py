# ruff: noqa: F811

import logging

import pytest

from ezrules.backend import shadow_evaluation_queue
from ezrules.core.rule_updater import SHADOW_CONFIG_LABEL, deploy_rule_to_shadow
from ezrules.models.backend_core import AllowedOutcome, FeatureDefinition
from ezrules.models.backend_core import Rule as RuleModel
from ezrules.models.backend_core import RuleEngineConfig, ShadowResultsLog
from tests.test_api_v2_rollouts import (  # noqa: F401
    active_rollout_rule,
    rollout_test_client,
)
from tests.test_api_v2_shadow import (  # noqa: F401
    shadow_rule,
    shadow_test_client,
)
from tests.test_shadow_evaluation_queue import (  # noqa: F401
    FakeRedis,
    _create_decision,
    _create_shadow_rule,
    fake_shadow_redis,
)


def test_shadow_deployment_rejects_predicate_return(
    shadow_test_client,
    shadow_rule,
) -> None:
    token = shadow_test_client.test_data["token"]
    session = shadow_test_client.test_data["session"]

    response = shadow_test_client.post(
        f"/api/v2/rules/{shadow_rule.r_id}/shadow",
        json={"logic": "return $amount > 100", "description": "Invalid candidate"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 400
    assert "direct configured outcome" in response.json()["detail"]
    shadow_config = (
        session.query(RuleEngineConfig)
        .filter(RuleEngineConfig.label == SHADOW_CONFIG_LABEL, RuleEngineConfig.o_id == shadow_rule.o_id)
        .first()
    )
    assert shadow_config is None or shadow_config.config == []


@pytest.mark.parametrize(
    ("legacy_logic", "error_fragment"),
    [
        ("return $amount > 100", "Invalid shadow candidate rule"),
        ("return !LEGACY_UNKNOWN", "is not configured in Outcomes"),
    ],
)
def test_shadow_promotion_revalidates_legacy_stored_candidate(
    shadow_test_client,
    shadow_rule,
    legacy_logic,
    error_fragment,
) -> None:
    token = shadow_test_client.test_data["token"]
    session = shadow_test_client.test_data["session"]
    original_logic = str(shadow_rule.logic)
    deploy_rule_to_shadow(
        db=session,
        o_id=int(shadow_rule.o_id),
        rule_model=shadow_rule,
        changed_by="legacy-seed",
        logic_override=legacy_logic,
    )

    response = shadow_test_client.post(
        f"/api/v2/rules/{shadow_rule.r_id}/shadow/promote",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 400
    assert error_fragment in response.json()["detail"]
    session.expire_all()
    assert str(session.get(RuleModel, shadow_rule.r_id).logic) == original_logic
    shadow_config = (
        session.query(RuleEngineConfig)
        .filter(RuleEngineConfig.label == SHADOW_CONFIG_LABEL, RuleEngineConfig.o_id == shadow_rule.o_id)
        .one()
    )
    assert next(entry for entry in shadow_config.config if entry["r_id"] == shadow_rule.r_id)["logic"] == legacy_logic


@pytest.mark.parametrize("invalid_logic", ["return $amount > 100", "invalid {{{ syntax"])
def test_invalid_legacy_shadow_payload_is_acknowledged_without_blocking_valid_work(
    session,
    fake_shadow_redis: FakeRedis,
    caplog,
    invalid_logic,
) -> None:
    rule = _create_shadow_rule(session)
    invalid_decision_id = _create_decision(session, int(rule.o_id))
    deploy_rule_to_shadow(
        db=session,
        o_id=int(rule.o_id),
        rule_model=rule,
        changed_by="legacy-seed",
        logic_override=invalid_logic,
    )
    shadow_evaluation_queue.enqueue_shadow_evaluation(
        db=session,
        evaluation_decision_id=invalid_decision_id,
        o_id=int(rule.o_id),
        transaction_id="invalid-shadow-result",
        event_data={"amount": 200},
        production_all_rule_results={int(rule.r_id): "HOLD"},
    )

    valid_decision_id = _create_decision(session, int(rule.o_id))
    deploy_rule_to_shadow(
        db=session,
        o_id=int(rule.o_id),
        rule_model=rule,
        changed_by="fixed-candidate",
        logic_override="return !REVIEW",
    )
    shadow_evaluation_queue.enqueue_shadow_evaluation(
        db=session,
        evaluation_decision_id=valid_decision_id,
        o_id=int(rule.o_id),
        transaction_id="valid-shadow-result",
        event_data={"amount": 200},
        production_all_rule_results={int(rule.r_id): "HOLD"},
    )

    with caplog.at_level(logging.ERROR, logger=shadow_evaluation_queue.__name__):
        drained = shadow_evaluation_queue.drain_shadow_evaluation_queue(batch_size=10, max_batches=1)

    assert drained["drained_messages"] == 2
    assert fake_shadow_redis.queue_contents(shadow_evaluation_queue.app_settings.SHADOW_EVALUATION_QUEUE_KEY) == []
    assert session.query(ShadowResultsLog).filter(ShadowResultsLog.ed_id == invalid_decision_id).count() == 0
    valid_log = session.query(ShadowResultsLog).filter(ShadowResultsLog.ed_id == valid_decision_id).one()
    assert str(valid_log.rule_result) == "REVIEW"
    assert "Dropping shadow evaluation with an invalid rule contract" in caplog.text


def test_valid_shadow_override_can_still_be_promoted(
    shadow_test_client,
    shadow_rule,
) -> None:
    token = shadow_test_client.test_data["token"]
    session = shadow_test_client.test_data["session"]

    deploy_response = shadow_test_client.post(
        f"/api/v2/rules/{shadow_rule.r_id}/shadow",
        json={"logic": "return !SHADOW_OUTCOME", "description": "Valid candidate"},
        headers={"Authorization": f"Bearer {token}"},
    )
    promote_response = shadow_test_client.post(
        f"/api/v2/rules/{shadow_rule.r_id}/shadow/promote",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert deploy_response.status_code == 200
    assert promote_response.status_code == 200
    session.expire_all()
    assert str(session.get(RuleModel, shadow_rule.r_id).logic) == "return !SHADOW_OUTCOME"


def test_rollout_promotion_revalidates_outcome_removed_after_deployment(
    rollout_test_client,
    active_rollout_rule,
) -> None:
    token = rollout_test_client.test_data["token"]
    session = rollout_test_client.test_data["session"]
    original_logic = str(active_rollout_rule.logic)
    deploy_response = rollout_test_client.post(
        f"/api/v2/rules/{active_rollout_rule.r_id}/rollout",
        json={"logic": "return !CANDIDATE", "description": "Candidate", "traffic_percent": 25},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert deploy_response.status_code == 200
    session.query(AllowedOutcome).filter(
        AllowedOutcome.o_id == active_rollout_rule.o_id,
        AllowedOutcome.outcome_name == "CANDIDATE",
    ).delete()
    session.commit()

    promote_response = rollout_test_client.post(
        f"/api/v2/rules/{active_rollout_rule.r_id}/rollout/promote",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert promote_response.status_code == 400
    assert "is not configured in Outcomes" in promote_response.json()["detail"]
    session.expire_all()
    assert str(session.get(RuleModel, active_rollout_rule.r_id).logic) == original_logic
    rollout_config = (
        session.query(RuleEngineConfig)
        .filter(RuleEngineConfig.label == "rollout", RuleEngineConfig.o_id == active_rollout_rule.o_id)
        .one()
    )
    assert next(entry for entry in rollout_config.config if entry["r_id"] == active_rollout_rule.r_id)["logic"] == (
        "return !CANDIDATE"
    )


def test_rollout_promotion_revalidates_feature_deactivated_after_deployment(
    rollout_test_client,
    active_rollout_rule,
) -> None:
    token = rollout_test_client.test_data["token"]
    session = rollout_test_client.test_data["session"]
    original_logic = str(active_rollout_rule.logic)
    feature = FeatureDefinition(
        o_id=active_rollout_rule.o_id,
        name="Sender sent amount 24h",
        entity="sender",
        feature_name="sent_amount_sum_24h",
        entity_key="sender_id",
        aggregation_type="sum",
        source_field="amount",
        window_seconds=86400,
        filters=[],
        status="active",
    )
    session.add(feature)
    session.commit()
    candidate_logic = "if stat[sender.sent_amount_sum_24h] > 100:\n\treturn !CANDIDATE\nreturn !CONTROL"
    deploy_response = rollout_test_client.post(
        f"/api/v2/rules/{active_rollout_rule.r_id}/rollout",
        json={"logic": candidate_logic, "description": "Candidate", "traffic_percent": 25},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert deploy_response.status_code == 200
    feature.status = "draft"
    session.commit()

    promote_response = rollout_test_client.post(
        f"/api/v2/rules/{active_rollout_rule.r_id}/rollout/promote",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert promote_response.status_code == 400
    assert "not active in Features" in promote_response.json()["detail"]
    session.expire_all()
    assert str(session.get(RuleModel, active_rollout_rule.r_id).logic) == original_logic
    rollout_config = (
        session.query(RuleEngineConfig)
        .filter(RuleEngineConfig.label == "rollout", RuleEngineConfig.o_id == active_rollout_rule.o_id)
        .one()
    )
    assert next(entry for entry in rollout_config.config if entry["r_id"] == active_rollout_rule.r_id)["logic"] == (
        candidate_logic
    )


def test_valid_rollout_candidate_can_still_be_promoted(
    rollout_test_client,
    active_rollout_rule,
) -> None:
    token = rollout_test_client.test_data["token"]
    session = rollout_test_client.test_data["session"]
    deploy_response = rollout_test_client.post(
        f"/api/v2/rules/{active_rollout_rule.r_id}/rollout",
        json={"logic": "return !CANDIDATE", "description": "Candidate", "traffic_percent": 25},
        headers={"Authorization": f"Bearer {token}"},
    )
    promote_response = rollout_test_client.post(
        f"/api/v2/rules/{active_rollout_rule.r_id}/rollout/promote",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert deploy_response.status_code == 200
    assert promote_response.status_code == 200
    session.expire_all()
    assert str(session.get(RuleModel, active_rollout_rule.r_id).logic) == "return !CANDIDATE"
