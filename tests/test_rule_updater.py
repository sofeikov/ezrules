from ezrules.core.rule_updater import RDBRuleEngineConfigProducer, RDBRuleManager
from ezrules.models.backend_core import Organisation, Rule, RuleEngineConfig


def test_updates_config_after_rule_update(session):
    org = session.query(Organisation).one()

    rule = Rule(logic="return 'HOLD'", description="1", rid="1", o_id=org.o_id)
    session.add(rule)
    session.commit()

    rm = RDBRuleManager(db=session, o_id=org.o_id)
    rule_engine_config_producer = RDBRuleEngineConfigProducer(db=session, o_id=org.o_id)
    rule_engine_config_producer.save_config(rm)

    db_config = session.query(RuleEngineConfig).one()
    assert db_config.config[0]["logic"] == "return 'HOLD'"

    rule.logic = "return 'CANCEL'"
    session.commit()
    rule_engine_config_producer.save_config(rm)
    db_config = session.query(RuleEngineConfig).one()
    assert db_config.config[0]["logic"] == "return 'CANCEL'"


def test_correct_revision_list_length(session):
    org = session.query(Organisation).one()
    rule = Rule(logic="return 'HOLD'", description="1", rid="1", o_id=org.o_id)
    session.add(rule)
    session.commit()

    rule.description = "2"
    session.commit()

    rule.description = "3"
    session.commit()

    rm = RDBRuleManager(db=session, o_id=org.o_id)
    assert len(rm.get_rule_revision_list(rule)) == 2
