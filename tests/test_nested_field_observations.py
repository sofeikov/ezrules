import json

import pytest

from ezrules.backend import observation_queue
from ezrules.backend.utils import record_observations
from ezrules.models.backend_core import FieldObservation, Organisation
from tests.test_observation_queue import FakeRedis


@pytest.fixture
def nested_fake_redis(monkeypatch: pytest.MonkeyPatch) -> FakeRedis:
    client = FakeRedis()
    monkeypatch.setattr(observation_queue, "get_observation_queue_client", lambda: client)
    return client


def _ensure_org(session) -> Organisation:
    org = session.query(Organisation).filter(Organisation.o_id == 1).first()
    if org is None:
        org = Organisation(o_id=1, name="Test Org")
        session.add(org)
        session.commit()
    return org


def test_record_observations_flattens_nested_paths(session):
    org = _ensure_org(session)

    record_observations(
        session,
        {
            "customer": {
                "profile": {"age": 21},
                "country": "US",
            }
        },
        int(org.o_id),
    )

    rows = (
        session.query(FieldObservation)
        .filter(FieldObservation.o_id == int(org.o_id))
        .order_by(FieldObservation.field_name, FieldObservation.observed_json_type)
        .all()
    )

    assert [(row.field_name, row.observed_json_type) for row in rows] == [
        ("customer", "dict"),
        ("customer.country", "str"),
        ("customer.profile", "dict"),
        ("customer.profile.age", "int"),
    ]


def test_enqueue_and_drain_observations_preserves_nested_paths(session, nested_fake_redis: FakeRedis):
    _ensure_org(session)

    queued = observation_queue.enqueue_observations(
        {"customer": {"profile": {"age": 21}, "country": "US"}},
        1,
    )

    assert queued is True
    payloads = nested_fake_redis.queue_contents(observation_queue.app_settings.OBSERVATION_QUEUE_KEY)
    assert len(payloads) == 1

    message = json.loads(payloads[0])
    assert message["observations"] == [
        {"field_name": "customer", "observed_json_type": "dict"},
        {"field_name": "customer.profile", "observed_json_type": "dict"},
        {"field_name": "customer.profile.age", "observed_json_type": "int"},
        {"field_name": "customer.country", "observed_json_type": "str"},
    ]

    drained = observation_queue.drain_observation_queue(batch_size=10, max_batches=1)

    assert drained == {"drained_batches": 1, "drained_messages": 1}
    rows = (
        session.query(FieldObservation)
        .filter(FieldObservation.o_id == 1)
        .order_by(FieldObservation.field_name, FieldObservation.observed_json_type)
        .all()
    )
    assert [(row.field_name, row.observed_json_type) for row in rows] == [
        ("customer", "dict"),
        ("customer.country", "str"),
        ("customer.profile", "dict"),
        ("customer.profile.age", "int"),
    ]
