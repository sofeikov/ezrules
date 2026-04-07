import json

import pytest

from ezrules.backend import shadow_evaluation_queue
from ezrules.backend.data_utils import Event, store_eval_result
from ezrules.core.rule_updater import RDBRuleEngineConfigProducer, RDBRuleManager, deploy_rule_to_shadow
from ezrules.models.backend_core import Organisation, Rule as RuleModel
from ezrules.models.backend_core import RuleDeploymentResultsLog, ShadowResultsLog


class FakeRedisLock:
    def __init__(self, state: dict[str, bool], name: str):
        self._state = state
        self._name = name
        self._held = False

    def acquire(self, blocking: bool = False) -> bool:
        del blocking
        if self._state.get(self._name, False):
            return False
        self._state[self._name] = True
        self._held = True
        return True

    def release(self) -> None:
        if self._held:
            self._state[self._name] = False
            self._held = False


class FakeRedis:
    def __init__(self) -> None:
        self._lists: dict[str, list[str]] = {}
        self._lock_state: dict[str, bool] = {}

    def lpush(self, name: str, *values: str) -> int:
        queue = self._lists.setdefault(name, [])
        for value in values:
            queue.insert(0, value)
        return len(queue)

    def rpush(self, name: str, *values: str) -> int:
        queue = self._lists.setdefault(name, [])
        queue.extend(values)
        return len(queue)

    def rpop(self, name: str, count: int | None = None) -> str | list[str] | None:
        queue = self._lists.setdefault(name, [])
        if not queue:
            return None
        if count is None:
            return queue.pop()

        popped: list[str] = []
        for _ in range(min(count, len(queue))):
            popped.append(queue.pop())
        return popped

    def lock(self, name: str, timeout: int | None = None, blocking: bool = False) -> FakeRedisLock:
        del timeout, blocking
        return FakeRedisLock(self._lock_state, name)

    def queue_contents(self, name: str) -> list[str]:
        return list(self._lists.get(name, []))


@pytest.fixture
def fake_shadow_redis(monkeypatch: pytest.MonkeyPatch) -> FakeRedis:
    client = FakeRedis()
    monkeypatch.setattr(shadow_evaluation_queue, "get_shadow_evaluation_queue_client", lambda: client)
    return client


def _ensure_org(session) -> Organisation:
    org = session.query(Organisation).filter(Organisation.o_id == 1).first()
    if org is None:
        org = Organisation(o_id=1, name="Test Org")
        session.add(org)
        session.commit()
    return org


def _create_shadow_rule(session) -> RuleModel:
    org = _ensure_org(session)
    rule = RuleModel(logic="return 'HOLD'", description="Shadow queue rule", rid="SHADOW_QUEUE:001", o_id=org.o_id)
    session.add(rule)
    session.commit()

    config_producer = RDBRuleEngineConfigProducer(db=session, o_id=org.o_id)
    config_producer.save_config(RDBRuleManager(db=session, o_id=org.o_id))
    deploy_rule_to_shadow(db=session, o_id=org.o_id, rule_model=rule, changed_by="test")
    return rule


def _create_testing_record(session, o_id: int) -> int:
    response = {
        "all_rule_results": {},
        "rule_results": {},
        "outcome_counters": {},
        "outcome_set": [],
    }
    _, tl_id = store_eval_result(
        db_session=session,
        o_id=o_id,
        event=Event(event_id="shadow-queue-event", event_timestamp=1234567890, event_data={"amount": 100}),
        response=response,
        commit=True,
    )
    return int(tl_id)


def test_enqueue_shadow_evaluation_serializes_shadow_snapshot(session, fake_shadow_redis: FakeRedis):
    rule = _create_shadow_rule(session)
    tl_id = _create_testing_record(session, int(rule.o_id))

    queued = shadow_evaluation_queue.enqueue_shadow_evaluation(
        db=session,
        tl_id=tl_id,
        o_id=int(rule.o_id),
        event_id="shadow-queue-event",
        event_data={"amount": 100},
        production_all_rule_results={int(rule.r_id): "HOLD"},
    )

    assert queued is True
    payloads = fake_shadow_redis.queue_contents(shadow_evaluation_queue.app_settings.SHADOW_EVALUATION_QUEUE_KEY)
    assert len(payloads) == 1

    payload = json.loads(payloads[0])
    assert payload["tl_id"] == tl_id
    assert payload["o_id"] == int(rule.o_id)
    assert payload["event_data"] == {"amount": 100}
    assert payload["production_all_rule_results"] == {str(int(rule.r_id)): "HOLD"}
    assert payload["shadow_config_version"] == 1
    assert payload["shadow_config"][0]["r_id"] == int(rule.r_id)


def test_drain_shadow_queue_uses_enqueued_config_snapshot(session, fake_shadow_redis: FakeRedis):
    rule = _create_shadow_rule(session)
    tl_id = _create_testing_record(session, int(rule.o_id))

    shadow_evaluation_queue.enqueue_shadow_evaluation(
        db=session,
        tl_id=tl_id,
        o_id=int(rule.o_id),
        event_id="shadow-queue-event",
        event_data={"amount": 100},
        production_all_rule_results={int(rule.r_id): "HOLD"},
    )

    deploy_rule_to_shadow(
        db=session,
        o_id=int(rule.o_id),
        rule_model=rule,
        changed_by="test",
        logic_override="return 'REVIEW'",
    )

    drained = shadow_evaluation_queue.drain_shadow_evaluation_queue(batch_size=10, max_batches=1)

    assert drained["drained_batches"] == 1
    assert drained["drained_messages"] == 1

    shadow_log = session.query(ShadowResultsLog).filter(ShadowResultsLog.tl_id == tl_id).one()
    assert shadow_log.rule_result == "HOLD"

    comparison_log = (
        session.query(RuleDeploymentResultsLog)
        .filter(
            RuleDeploymentResultsLog.tl_id == tl_id,
            RuleDeploymentResultsLog.mode == "shadow",
            RuleDeploymentResultsLog.r_id == int(rule.r_id),
        )
        .one()
    )
    assert comparison_log.candidate_result == "HOLD"
    assert comparison_log.control_result == "HOLD"


def test_drain_shadow_queue_requeues_on_persist_failure(
    session,
    fake_shadow_redis: FakeRedis,
    monkeypatch: pytest.MonkeyPatch,
):
    rule = _create_shadow_rule(session)
    tl_id = _create_testing_record(session, int(rule.o_id))

    shadow_evaluation_queue.enqueue_shadow_evaluation(
        db=session,
        tl_id=tl_id,
        o_id=int(rule.o_id),
        event_id="shadow-queue-event",
        event_data={"amount": 100},
        production_all_rule_results={int(rule.r_id): "HOLD"},
    )
    original_payloads = fake_shadow_redis.queue_contents(
        shadow_evaluation_queue.app_settings.SHADOW_EVALUATION_QUEUE_KEY
    )

    def _raise(payload):
        del payload
        raise RuntimeError("boom")

    monkeypatch.setattr(shadow_evaluation_queue, "_persist_shadow_results", _raise)

    with pytest.raises(RuntimeError, match="boom"):
        shadow_evaluation_queue.drain_shadow_evaluation_queue(batch_size=10, max_batches=1)

    assert (
        fake_shadow_redis.queue_contents(shadow_evaluation_queue.app_settings.SHADOW_EVALUATION_QUEUE_KEY)
        == original_payloads
    )


def test_drain_shadow_queue_skips_when_lock_is_held(session, fake_shadow_redis: FakeRedis):
    rule = _create_shadow_rule(session)
    tl_id = _create_testing_record(session, int(rule.o_id))

    shadow_evaluation_queue.enqueue_shadow_evaluation(
        db=session,
        tl_id=tl_id,
        o_id=int(rule.o_id),
        event_id="shadow-queue-event",
        event_data={"amount": 100},
        production_all_rule_results={int(rule.r_id): "HOLD"},
    )

    held_lock = fake_shadow_redis.lock(shadow_evaluation_queue.app_settings.SHADOW_EVALUATION_QUEUE_LOCK_KEY)
    assert held_lock.acquire() is True

    drained = shadow_evaluation_queue.drain_shadow_evaluation_queue(batch_size=10, max_batches=1)

    assert drained == {"drained_batches": 0, "drained_messages": 0, "max_enqueue_lag_seconds": 0}
    assert len(fake_shadow_redis.queue_contents(shadow_evaluation_queue.app_settings.SHADOW_EVALUATION_QUEUE_KEY)) == 1
