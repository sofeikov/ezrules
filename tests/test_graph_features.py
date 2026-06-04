import hashlib
import json
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from ezrules.backend.api_v2.main import app
from ezrules.backend.api_v2.routes import evaluator as evaluator_router
from ezrules.backend.features import compute_feature, persist_graph_links_for_event
from ezrules.backend.rule_executors.executors import LocalRuleExecutorSQL
from ezrules.core.rule_updater import RDBRuleEngineConfigProducer, RDBRuleManager
from ezrules.models.backend_core import (
    EventVersion,
    FeatureDefinition,
    GraphEntityField,
    GraphEventEntityLink,
    Organisation,
    Rule,
)


def _hash_payload(event_data: dict) -> str:
    serialized = json.dumps(event_data, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _configure_graph_fields(session, org_id: int) -> None:
    session.add_all(
        [
            GraphEntityField(o_id=org_id, field_path="user_id", entity_type="user"),
            GraphEntityField(o_id=org_id, field_path="account_id", entity_type="account"),
            GraphEntityField(o_id=org_id, field_path="card_fingerprint", entity_type="card"),
            GraphEntityField(o_id=org_id, field_path="device_id", entity_type="device"),
        ]
    )
    session.commit()


def _add_graph_event(
    session,
    org_id: int,
    transaction_id: str,
    effective_at: datetime,
    event_data: dict,
    *,
    observed_at: datetime | None = None,
) -> EventVersion:
    latest = (
        session.query(EventVersion)
        .filter(EventVersion.o_id == org_id, EventVersion.transaction_id == transaction_id)
        .order_by(EventVersion.event_version.desc(), EventVersion.ev_id.desc())
        .first()
    )
    event_version_number = 1 if latest is None else int(latest.event_version) + 1
    event_version = EventVersion(
        o_id=org_id,
        transaction_id=transaction_id,
        event_version=event_version_number,
        effective_at=effective_at,
        observed_at=observed_at or effective_at,
        event_data=event_data,
        payload_hash=_hash_payload(event_data),
        supersedes_ev_id=None if latest is None else int(latest.ev_id),
    )
    session.add(event_version)
    session.flush()
    persist_graph_links_for_event(session, org_id, event_version)
    session.commit()
    return event_version


def _graph_feature(org_id: int) -> FeatureDefinition:
    return FeatureDefinition(
        o_id=org_id,
        name="User unique cards through graph 90d",
        entity="user",
        feature_name="unique_cards_graph_90d",
        feature_kind="graph",
        entity_key="user_id",
        aggregation_type="graph_distinct_count",
        source_field=None,
        window_seconds=7776000,
        filters=[],
        graph_config={
            "target_entity": "card",
            "allowed_entity_types": ["user", "account", "card", "device"],
            "max_depth": 4,
            "max_expanded_nodes": 1000,
        },
        status="active",
    )


def test_persist_graph_links_for_event_extracts_configured_entity_fields(session):
    org = session.query(Organisation).one()
    _configure_graph_fields(session, int(org.o_id))

    event_version = _add_graph_event(
        session,
        int(org.o_id),
        "txn-graph-links",
        datetime(2026, 6, 1, 12, 0, tzinfo=UTC),
        {
            "user_id": "user-1",
            "account_id": "account-1",
            "card_fingerprint": "card-1",
            "ignored_field": "ignored",
        },
    )

    links = (
        session.query(GraphEventEntityLink)
        .filter(GraphEventEntityLink.ev_id == int(event_version.ev_id))
        .order_by(GraphEventEntityLink.entity_type.asc())
        .all()
    )

    assert [(str(link.entity_type), str(link.entity_value)) for link in links] == [
        ("account", "account-1"),
        ("card", "card-1"),
        ("user", "user-1"),
    ]


def test_graph_distinct_count_traverses_bounded_transaction_links(session):
    org = session.query(Organisation).one()
    org_id = int(org.o_id)
    _configure_graph_fields(session, org_id)
    feature = _graph_feature(org_id)
    session.add(feature)
    session.commit()

    effective_at = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    _add_graph_event(session, org_id, "txn-user-account", effective_at, {"user_id": "user-1", "account_id": "acct-1"})
    _add_graph_event(
        session, org_id, "txn-account-card-1", effective_at, {"account_id": "acct-1", "card_fingerprint": "card-1"}
    )
    _add_graph_event(
        session, org_id, "txn-account-card-2", effective_at, {"account_id": "acct-1", "card_fingerprint": "card-2"}
    )
    _add_graph_event(session, org_id, "txn-user-device", effective_at, {"user_id": "user-1", "device_id": "device-1"})
    _add_graph_event(
        session, org_id, "txn-device-card", effective_at, {"device_id": "device-1", "card_fingerprint": "card-3"}
    )
    _add_graph_event(
        session, org_id, "txn-other-account-card", effective_at, {"account_id": "acct-9", "card_fingerprint": "card-9"}
    )

    result = compute_feature(
        session,
        org_id,
        feature,
        {"user_id": "user-1"},
        datetime(2026, 6, 2, 12, 0, tzinfo=UTC),
    )

    assert result.value == 3
    assert result.matched_event_count == 5


def test_graph_distinct_count_uses_current_transaction_version_as_of_time(session):
    org = session.query(Organisation).one()
    org_id = int(org.o_id)
    _configure_graph_fields(session, org_id)
    feature = _graph_feature(org_id)
    session.add(feature)
    session.commit()

    effective_at = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    _add_graph_event(
        session,
        org_id,
        "txn-rescore",
        effective_at,
        {"user_id": "user-1", "card_fingerprint": "card-old"},
        observed_at=datetime(2026, 6, 1, 12, 1, tzinfo=UTC),
    )
    _add_graph_event(
        session,
        org_id,
        "txn-rescore",
        effective_at,
        {"user_id": "user-1", "card_fingerprint": "card-new", "document_id": "doc-1"},
        observed_at=datetime(2026, 6, 2, 12, 1, tzinfo=UTC),
    )

    before_correction = compute_feature(
        session,
        org_id,
        feature,
        {"user_id": "user-1"},
        datetime(2026, 6, 1, 13, 0, tzinfo=UTC),
    )
    after_correction = compute_feature(
        session,
        org_id,
        feature,
        {"user_id": "user-1"},
        datetime(2026, 6, 3, 12, 0, tzinfo=UTC),
    )

    assert before_correction.value == 1
    assert before_correction.matched_event_count == 1
    assert after_correction.value == 1
    assert after_correction.matched_event_count == 1


def test_evaluate_uses_graph_feature_stat_in_rule(session, live_api_key):
    org = session.query(Organisation).one()
    org_id = int(org.o_id)
    _configure_graph_fields(session, org_id)
    session.add(_graph_feature(org_id))
    session.add(
        Rule(
            logic="if stat[user.unique_cards_graph_90d] >= 3:\n\treturn !HOLD",
            description="Hold users connected to too many cards",
            rid="GRAPH:001",
            o_id=org_id,
            r_id=9301,
        )
    )
    session.commit()

    effective_at = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    _add_graph_event(session, org_id, "txn-user-account", effective_at, {"user_id": "user-1", "account_id": "acct-1"})
    _add_graph_event(
        session, org_id, "txn-account-card-1", effective_at, {"account_id": "acct-1", "card_fingerprint": "card-1"}
    )
    _add_graph_event(
        session, org_id, "txn-account-card-2", effective_at, {"account_id": "acct-1", "card_fingerprint": "card-2"}
    )
    _add_graph_event(session, org_id, "txn-user-device", effective_at, {"user_id": "user-1", "device_id": "device-1"})
    _add_graph_event(
        session, org_id, "txn-device-card", effective_at, {"device_id": "device-1", "card_fingerprint": "card-3"}
    )

    config_producer = RDBRuleEngineConfigProducer(db=session, o_id=org_id)
    config_producer.save_config(RDBRuleManager(db=session, o_id=org_id))
    evaluator_router._lre = LocalRuleExecutorSQL(db=session, o_id=org_id)

    with TestClient(app) as client:
        response = client.post(
            "/api/v2/evaluate",
            json={
                "transaction_id": "txn-current",
                "effective_at": "2026-06-02T12:00:00Z",
                "event_data": {"user_id": "user-1", "amount": 25},
            },
            headers={"X-API-Key": live_api_key},
        )

    evaluator_router._lre = None
    assert response.status_code == 200
    assert response.json()["rule_results"]["9301"] == "HOLD"
