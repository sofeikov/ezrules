import json


from ezrules.core.rule_updater import (RDBRuleEngineConfigProducer, RDBRuleManager)
from ezrules.models.backend_core import Organisation, Rule


def test_ping(logged_out_eval_client):
    rv = logged_out_eval_client.get(f"/ping")
    assert rv.data.decode() == "OK"


def test_can_evaluate_rule(session, logged_out_eval_client):

    org = session.query(Organisation).one()

    rule = Rule(logic="return 'HOLD'", description="1", rid="1", o_id=org.o_id)
    session.add(rule)
    session.commit()

    rm = RDBRuleManager(db=session, o_id=org.o_id)
    rule_engine_config_producer = RDBRuleEngineConfigProducer(db=session, o_id=org.o_id)

    rule_engine_config_producer.save_config(rm)

    rv = logged_out_eval_client.post("/evaluate", json={"A": 1})
    assert json.loads(rv.data.decode()) == ["HOLD"]
