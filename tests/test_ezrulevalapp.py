import json

from ezrules.core.rule_updater import RDBRuleEngineConfigProducer, RDBRuleManager
from ezrules.models.backend_core import Organisation, Rule


def test_ping(logged_out_eval_client):
    rv = logged_out_eval_client.get("/ping")
    assert rv.data.decode() == "OK"


def test_can_evaluate_rule(session, logged_out_eval_client):
    org = session.query(Organisation).one()

    rule = Rule(logic="return 'HOLD'", description="1", rid="1", o_id=org.o_id, r_id=123)
    session.add(rule)
    session.commit()

    rm = RDBRuleManager(db=session, o_id=org.o_id)
    rule_engine_config_producer = RDBRuleEngineConfigProducer(db=session, o_id=org.o_id)

    rule_engine_config_producer.save_config(rm)

    rv = logged_out_eval_client.post(
        "/evaluate",
        json={"event_id": "1", "event_timestamp": 2, "event_data": {"A": 2}},
    )
    result = json.loads(rv.data.decode())
    assert result["outcome_counters"] == {"HOLD": 1}
    assert result["outcome_set"] == ["HOLD"]
    assert result["rule_results"] == {"123": "HOLD"}
