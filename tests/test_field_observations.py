"""
Integration tests for field observation collection via /evaluate.

Verifies that FieldObservation rows are created/updated in the DB
after each successful evaluation call.
"""

from fastapi.testclient import TestClient

from ezrules.backend.api_v2.main import app
from ezrules.backend.api_v2.routes import evaluator as evaluator_router
from ezrules.backend.rule_executors.executors import LocalRuleExecutorSQL
from ezrules.core.rule_updater import RDBRuleEngineConfigProducer, RDBRuleManager
from ezrules.models.backend_core import FieldObservation, Organisation, Rule


def _setup_rule(session, rid, r_id):
    """Create a minimal rule and persist a rule engine config."""
    org = session.query(Organisation).one()
    rule = Rule(logic="return 'HOLD'", description="obs test rule", rid=rid, o_id=org.o_id, r_id=r_id)
    session.add(rule)
    session.commit()
    RDBRuleEngineConfigProducer(db=session, o_id=org.o_id).save_config(RDBRuleManager(db=session, o_id=org.o_id))
    evaluator_router._lre = LocalRuleExecutorSQL(db=session, o_id=org.o_id)
    return org


class TestFieldObservationCollection:
    def test_observations_created_after_evaluate(self, session, live_api_key):
        """Fields in event_data should appear in FieldObservation after /evaluate."""
        org = _setup_rule(session, "OBS:001", 8001)

        with TestClient(app) as client:
            client.post(
                "/api/v2/evaluate",
                json={
                    "event_id": "obs_test_1",
                    "event_timestamp": 1700000000,
                    "event_data": {"amount": 500, "country": "US"},
                },
                headers={"X-API-Key": live_api_key},
            )

        evaluator_router._lre = None

        amount_obs = (
            session.query(FieldObservation)
            .filter(FieldObservation.field_name == "amount", FieldObservation.o_id == org.o_id)
            .first()
        )
        country_obs = (
            session.query(FieldObservation)
            .filter(FieldObservation.field_name == "country", FieldObservation.o_id == org.o_id)
            .first()
        )

        assert amount_obs is not None
        assert amount_obs.observed_json_type == "int"
        assert amount_obs.occurrence_count == 1

        assert country_obs is not None
        assert country_obs.observed_json_type == "str"
        assert country_obs.occurrence_count == 1

    def test_observation_count_increments_on_repeat_evaluate(self, session, live_api_key):
        """Repeated /evaluate calls should increment occurrence_count."""
        org = _setup_rule(session, "OBS:002", 8002)

        with TestClient(app) as client:
            for i in range(3):
                client.post(
                    "/api/v2/evaluate",
                    json={
                        "event_id": f"obs_repeat_{i}",
                        "event_timestamp": 1700000000,
                        "event_data": {"score": 1.5},
                    },
                    headers={"X-API-Key": live_api_key},
                )

        evaluator_router._lre = None

        obs = (
            session.query(FieldObservation)
            .filter(FieldObservation.field_name == "score", FieldObservation.o_id == org.o_id)
            .first()
        )
        assert obs is not None
        assert obs.occurrence_count == 3

    def test_observation_per_type_on_type_change(self, session, live_api_key):
        """Each distinct type for a field gets its own row with its own count."""
        org = _setup_rule(session, "OBS:003", 8003)

        with TestClient(app) as client:
            client.post(
                "/api/v2/evaluate",
                json={
                    "event_id": "obs_type_1",
                    "event_timestamp": 1700000000,
                    "event_data": {"ref": 123},
                },
                headers={"X-API-Key": live_api_key},
            )
            client.post(
                "/api/v2/evaluate",
                json={
                    "event_id": "obs_type_2",
                    "event_timestamp": 1700000000,
                    "event_data": {"ref": "ABC"},
                },
                headers={"X-API-Key": live_api_key},
            )

        evaluator_router._lre = None

        rows = (
            session.query(FieldObservation)
            .filter(FieldObservation.field_name == "ref", FieldObservation.o_id == org.o_id)
            .all()
        )
        assert len(rows) == 2
        by_type = {r.observed_json_type: r.occurrence_count for r in rows}
        assert by_type == {"int": 1, "str": 1}
