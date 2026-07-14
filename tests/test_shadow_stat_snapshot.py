import json
from datetime import UTC, datetime, timedelta
from typing import Any

from ezrules.backend import shadow_evaluation_queue
from ezrules.backend.api_v2.routes import evaluator as evaluator_router
from ezrules.backend.data_utils import Event, store_eval_result
from ezrules.core.rule_updater import (
    RDBRuleEngineConfigProducer,
    RDBRuleManager,
    deploy_rule_to_shadow,
    get_deployment_config,
)
from ezrules.core.user_lists import PersistentUserListManager
from ezrules.models.backend_core import EventVersion, FeatureDefinition, Organisation, ShadowResultsLog
from ezrules.models.backend_core import Rule as RuleModel
from tests.canonical_helpers import _hash_payload

SHADOW_STAT_PATH = "sender.shadow_only_amount_sum_24h"
SHADOW_STAT_LOGIC = f"if stat[{SHADOW_STAT_PATH}] >= 100:\n\treturn !ESCALATE"


class CapturingRedis:
    def __init__(self) -> None:
        self.payloads: list[str] = []

    def lpush(self, _name: str, *values: str) -> int:
        for value in values:
            self.payloads.insert(0, value)
        return len(self.payloads)


class RuleStatsStub:
    def get_rule_stats(self) -> set[str]:
        return set()


def _ensure_org(session) -> Organisation:
    org = session.query(Organisation).filter(Organisation.o_id == 1).first()
    if org is None:
        org = Organisation(o_id=1, name="Shadow stat snapshot org")
        session.add(org)
        session.commit()
    return org


def _create_decision(session, *, o_id: int, event_id: str, as_of: datetime) -> int:
    response: dict[str, Any] = {
        "all_rule_results": {},
        "rule_results": {},
        "outcome_counters": {},
        "outcome_set": [],
    }
    _, decision_id = store_eval_result(
        db_session=session,
        o_id=o_id,
        event=Event(transaction_id=event_id, effective_at=as_of, event_data={"sender_id": "S1"}),
        response=response,
        commit=True,
    )
    return int(decision_id)


def test_shadow_only_stat_and_config_use_one_snapshot(session, monkeypatch) -> None:
    org = _ensure_org(session)
    org_id = int(org.o_id)
    as_of = datetime.now(UTC).replace(microsecond=0)
    prior_event_data = {"amount": 125, "sender_id": "S1"}
    session.add_all(
        [
            FeatureDefinition(
                o_id=org_id,
                name="Shadow-only sender amount 24h",
                entity="sender",
                feature_name="shadow_only_amount_sum_24h",
                entity_key="sender_id",
                aggregation_type="sum",
                source_field="amount",
                window_seconds=86400,
                filters=[],
                status="active",
            ),
            EventVersion(
                o_id=org_id,
                transaction_id="shadow-stat-prior-event",
                event_version=1,
                effective_at=as_of - timedelta(hours=1),
                observed_at=as_of - timedelta(hours=1),
                event_data=prior_event_data,
                payload_hash=_hash_payload(prior_event_data),
            ),
        ]
    )
    rule = RuleModel(
        logic="return !HOLD",
        description="Shadow-only stat snapshot rule",
        rid="SHADOW:STAT:SNAPSHOT",
        o_id=org_id,
    )
    session.add(rule)
    session.commit()
    RDBRuleEngineConfigProducer(db=session, o_id=org_id).save_config(RDBRuleManager(db=session, o_id=org_id))
    deploy_rule_to_shadow(
        db=session,
        o_id=org_id,
        rule_model=rule,
        changed_by="test",
        logic_override=SHADOW_STAT_LOGIC,
    )

    shadow_snapshot = shadow_evaluation_queue.load_shadow_evaluation_snapshot(session, org_id)
    assert shadow_snapshot is not None
    list_provider = PersistentUserListManager(session, org_id)
    stats, _traces = evaluator_router._resolve_evaluation_stats(
        db=session,
        o_id=org_id,
        event_data={"sender_id": "S1"},
        as_of=as_of,
        lre=RuleStatsStub(),  # type: ignore[arg-type]
        rollout_entries=[],
        shadow_entries=list(shadow_snapshot.config),
        list_provider=list_provider,
    )
    assert stats[SHADOW_STAT_PATH] == 125

    deploy_rule_to_shadow(
        db=session,
        o_id=org_id,
        rule_model=rule,
        changed_by="test",
        logic_override="return !REVIEW",
    )
    current_config = get_deployment_config(session, o_id=org_id, label="shadow")
    assert current_config is not None
    assert int(current_config.version) > shadow_snapshot.config_version

    fake_redis = CapturingRedis()
    monkeypatch.setattr(shadow_evaluation_queue, "get_shadow_evaluation_queue_client", lambda: fake_redis)
    decision_id = _create_decision(
        session,
        o_id=org_id,
        event_id="shadow-stat-snapshot-evaluation",
        as_of=as_of,
    )
    assert shadow_evaluation_queue.enqueue_shadow_evaluation(
        db=session,
        o_id=org_id,
        event_id="shadow-stat-snapshot-evaluation",
        event_data={"sender_id": "S1"},
        stats=stats,
        production_all_rule_results={},
        evaluation_decision_id=decision_id,
        shadow_snapshot=shadow_snapshot,
    )

    payload = json.loads(fake_redis.payloads[0])
    assert payload["stats"][SHADOW_STAT_PATH] == 125
    assert payload["shadow_config_version"] == shadow_snapshot.config_version
    assert payload["shadow_config"][0]["logic"] == SHADOW_STAT_LOGIC

    persisted = shadow_evaluation_queue._persist_shadow_results(payload)
    assert persisted == 1
    shadow_log = session.query(ShadowResultsLog).filter(ShadowResultsLog.ed_id == decision_id).one()
    assert shadow_log.rule_result == "ESCALATE"
