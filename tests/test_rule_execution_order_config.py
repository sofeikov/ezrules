from ezrules.core.rule_updater import RDBRuleEngineConfigProducer, RDBRuleManager
from ezrules.models.backend_core import Organisation, RuleEngineConfig, RuleStatus
from ezrules.models.backend_core import Rule as RuleModel


def test_production_config_orders_main_rules_by_execution_order(session):
    org = session.query(Organisation).one()
    session.add_all(
        [
            RuleModel(
                logic="return !RELEASE",
                description="Runs second",
                rid="MAIN_SECOND",
                execution_order=20,
                evaluation_lane="main",
                status=RuleStatus.ACTIVE,
                o_id=org.o_id,
                r_id=9301,
            ),
            RuleModel(
                logic="return !HOLD",
                description="Runs first",
                rid="MAIN_FIRST",
                execution_order=10,
                evaluation_lane="main",
                status=RuleStatus.ACTIVE,
                o_id=org.o_id,
                r_id=9302,
            ),
        ]
    )
    session.commit()

    config_producer = RDBRuleEngineConfigProducer(db=session, o_id=org.o_id)
    config_producer.save_config(RDBRuleManager(db=session, o_id=org.o_id))

    config = (
        session.query(RuleEngineConfig)
        .filter(RuleEngineConfig.o_id == org.o_id, RuleEngineConfig.label == "production")
        .one()
    )

    assert [int(item["r_id"]) for item in config.config] == [9302, 9301]
