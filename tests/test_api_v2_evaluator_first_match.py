import hashlib
import secrets
import uuid

from fastapi.testclient import TestClient

from ezrules.backend.api_v2.main import app
from ezrules.backend.api_v2.routes import evaluator as evaluator_router
from ezrules.core.rule_updater import RDBRuleEngineConfigProducer, RDBRuleManager
from ezrules.models.backend_core import (
    ApiKey,
    EvaluationDecision,
    EvaluationRuleResult,
    Organisation,
    RuleStatus,
    RuntimeSetting,
)
from ezrules.models.backend_core import Rule as RuleModel


def _create_api_key(session, org_id: int) -> str:
    raw_key = "ezrk_" + secrets.token_hex(32)
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    api_key = ApiKey(
        gid=str(uuid.uuid4()),
        key_hash=key_hash,
        label="first-match-eval-key",
        o_id=org_id,
    )
    session.add(api_key)
    session.commit()
    return raw_key


def test_evaluate_first_match_uses_main_rule_execution_order(session):
    org = session.query(Organisation).one()
    api_key = _create_api_key(session, int(org.o_id))

    session.add(
        RuntimeSetting(
            key="main_rule_execution_mode",
            o_id=int(org.o_id),
            value_type="string",
            value="first_match",
        )
    )
    session.add_all(
        [
            RuleModel(
                logic="return !RELEASE",
                description="Runs second",
                rid="FIRST_MATCH_SECOND",
                execution_order=2,
                evaluation_lane="main",
                status=RuleStatus.ACTIVE,
                o_id=org.o_id,
                r_id=9401,
            ),
            RuleModel(
                logic="return !HOLD",
                description="Runs first",
                rid="FIRST_MATCH_FIRST",
                execution_order=1,
                evaluation_lane="main",
                status=RuleStatus.ACTIVE,
                o_id=org.o_id,
                r_id=9402,
            ),
        ]
    )
    session.commit()

    config_producer = RDBRuleEngineConfigProducer(db=session, o_id=org.o_id)
    config_producer.save_config(RDBRuleManager(db=session, o_id=org.o_id))

    evaluator_router._lre = None
    evaluator_router._shadow_lre = None
    evaluator_router._allowlist_lre = None

    with TestClient(app) as client:
        response = client.post(
            "/api/v2/evaluate",
            json={
                "event_id": "first-match-main-order",
                "event_timestamp": 1234567890,
                "event_data": {"amount": 500},
            },
            headers={"X-API-Key": api_key},
        )

    evaluator_router._lre = None
    evaluator_router._shadow_lre = None
    evaluator_router._allowlist_lre = None

    assert response.status_code == 200
    payload = response.json()
    assert payload["resolved_outcome"] == "HOLD"
    assert payload["outcome_counters"] == {"HOLD": 1}
    assert payload["rule_results"] == {"9402": "HOLD"}

    stored_event = session.query(EvaluationDecision).filter_by(event_id="first-match-main-order").one()
    assert stored_event.resolved_outcome == "HOLD"
    assert stored_event.outcome_counters == {"HOLD": 1}

    stored_results = (
        session.query(EvaluationRuleResult)
        .filter(EvaluationRuleResult.ed_id == stored_event.ed_id)
        .order_by(EvaluationRuleResult.r_id.asc())
        .all()
    )
    assert [int(result.r_id) for result in stored_results] == [9402]
    assert [str(result.rule_result) for result in stored_results] == ["HOLD"]
