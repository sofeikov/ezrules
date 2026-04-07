import json

import pytest

from ezrules.backend import observation_queue
from ezrules.models.backend_core import FieldObservation


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
def fake_redis(monkeypatch: pytest.MonkeyPatch) -> FakeRedis:
    client = FakeRedis()
    monkeypatch.setattr(observation_queue, "get_observation_queue_client", lambda: client)
    return client


def test_enqueue_observations_serializes_field_types(fake_redis: FakeRedis):
    queued = observation_queue.enqueue_observations({"amount": 500, "country": "US"}, 42)

    assert queued is True
    payloads = fake_redis.queue_contents(observation_queue.app_settings.OBSERVATION_QUEUE_KEY)
    assert len(payloads) == 1

    message = json.loads(payloads[0])
    assert message["o_id"] == 42
    assert message["observations"] == [
        {"field_name": "amount", "observed_json_type": "int"},
        {"field_name": "country", "observed_json_type": "str"},
    ]


def test_drain_observation_queue_persists_distinct_observation_rows(session, fake_redis: FakeRedis):
    observation_queue.enqueue_observations({"amount": 500, "country": "US"}, 1)
    observation_queue.enqueue_observations({"amount": 700, "country": "GB"}, 1)
    observation_queue.enqueue_observations({"amount": "700"}, 1)

    drained = observation_queue.drain_observation_queue(batch_size=10, max_batches=2)

    assert drained == {"drained_batches": 1, "drained_messages": 3}

    rows = (
        session.query(FieldObservation)
        .filter(FieldObservation.o_id == 1)
        .order_by(FieldObservation.field_name, FieldObservation.observed_json_type)
        .all()
    )
    assert [(row.field_name, row.observed_json_type) for row in rows] == [
        ("amount", "int"),
        ("amount", "str"),
        ("country", "str"),
    ]


def test_drain_observation_queue_requeues_on_upsert_failure(
    monkeypatch: pytest.MonkeyPatch,
    fake_redis: FakeRedis,
):
    observation_queue.enqueue_observations({"amount": 500}, 1)
    original_payloads = fake_redis.queue_contents(observation_queue.app_settings.OBSERVATION_QUEUE_KEY)

    def _raise(*args, **kwargs):
        del args, kwargs
        raise RuntimeError("boom")

    monkeypatch.setattr(observation_queue, "upsert_field_observations", _raise)

    with pytest.raises(RuntimeError, match="boom"):
        observation_queue.drain_observation_queue(batch_size=10, max_batches=1)

    assert fake_redis.queue_contents(observation_queue.app_settings.OBSERVATION_QUEUE_KEY) == original_payloads


def test_drain_observation_queue_skips_when_lock_is_held(fake_redis: FakeRedis):
    observation_queue.enqueue_observations({"amount": 500}, 1)
    held_lock = fake_redis.lock(observation_queue.app_settings.OBSERVATION_QUEUE_LOCK_KEY)
    assert held_lock.acquire() is True

    drained = observation_queue.drain_observation_queue(batch_size=10, max_batches=1)

    assert drained == {"drained_batches": 0, "drained_messages": 0}
    assert len(fake_redis.queue_contents(observation_queue.app_settings.OBSERVATION_QUEUE_KEY)) == 1
