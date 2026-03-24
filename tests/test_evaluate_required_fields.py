from fastapi.testclient import TestClient

from ezrules.backend.api_v2.main import app
from ezrules.backend.api_v2.routes import evaluator as evaluator_router
from ezrules.backend.rule_executors.executors import LocalRuleExecutorSQL
from ezrules.core.rule_updater import RDBRuleEngineConfigProducer, RDBRuleManager
from ezrules.models.backend_core import FieldTypeConfig, Organisation, Rule, TestingRecordLog


def _setup_rule_engine(session, *, rid: str, r_id: int, logic: str):
    org = session.query(Organisation).one()
    rule = Rule(logic=logic, description="evaluation contract test rule", rid=rid, o_id=org.o_id, r_id=r_id)
    session.add(rule)
    session.commit()
    RDBRuleEngineConfigProducer(db=session, o_id=org.o_id).save_config(RDBRuleManager(db=session, o_id=org.o_id))
    evaluator_router._lre = LocalRuleExecutorSQL(db=session, o_id=org.o_id)
    return org


class TestEvaluateRequiredFieldContracts:
    def test_missing_required_field_returns_400_without_persisting(self, session, live_api_key):
        org = _setup_rule_engine(
            session,
            rid="REQ:EVAL:001",
            r_id=9301,
            logic="return 'PASS'",
        )
        session.add(FieldTypeConfig(field_name="amount", configured_type="integer", required=True, o_id=org.o_id))
        session.commit()

        with TestClient(app) as client:
            response = client.post(
                "/api/v2/evaluate",
                json={
                    "event_id": "required_missing_eval",
                    "event_timestamp": 1700000000,
                    "event_data": {"country": "US"},
                },
                headers={"X-API-Key": live_api_key},
            )

        evaluator_router._lre = None

        assert response.status_code == 400
        assert "amount" in response.json()["detail"]
        assert (
            session.query(TestingRecordLog)
            .filter(TestingRecordLog.event_id == "required_missing_eval", TestingRecordLog.o_id == org.o_id)
            .count()
            == 0
        )

    def test_null_required_field_returns_400_without_persisting(self, session, live_api_key):
        org = _setup_rule_engine(
            session,
            rid="REQ:EVAL:002",
            r_id=9302,
            logic="return 'PASS'",
        )
        session.add(FieldTypeConfig(field_name="amount", configured_type="integer", required=True, o_id=org.o_id))
        session.commit()

        with TestClient(app) as client:
            response = client.post(
                "/api/v2/evaluate",
                json={
                    "event_id": "required_null_eval",
                    "event_timestamp": 1700000000,
                    "event_data": {"amount": None},
                },
                headers={"X-API-Key": live_api_key},
            )

        evaluator_router._lre = None

        assert response.status_code == 400
        assert "amount" in response.json()["detail"]
        assert (
            session.query(TestingRecordLog)
            .filter(TestingRecordLog.event_id == "required_null_eval", TestingRecordLog.o_id == org.o_id)
            .count()
            == 0
        )

    def test_missing_non_required_lookup_returns_clear_400_without_persisting(self, session, live_api_key):
        org = _setup_rule_engine(
            session,
            rid="REQ:EVAL:003",
            r_id=9303,
            logic='if $country == "US":\n\treturn "HOLD"',
        )

        with TestClient(app) as client:
            response = client.post(
                "/api/v2/evaluate",
                json={
                    "event_id": "strict_lookup_missing_eval",
                    "event_timestamp": 1700000000,
                    "event_data": {"amount": 100},
                },
                headers={"X-API-Key": live_api_key},
            )

        evaluator_router._lre = None

        assert response.status_code == 400
        assert "country" in response.json()["detail"]
        assert "lookup failed" in response.json()["detail"]
        assert (
            session.query(TestingRecordLog)
            .filter(TestingRecordLog.event_id == "strict_lookup_missing_eval", TestingRecordLog.o_id == org.o_id)
            .count()
            == 0
        )
