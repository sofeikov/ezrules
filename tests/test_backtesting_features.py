"""Backtesting with point-in-time computed stat resolution."""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from ezrules.backend.api_v2.main import app
from ezrules.backend.api_v2.routes import evaluator as evaluator_router
from ezrules.backend.backtesting import BacktestRecord, compute_backtest_metrics
from ezrules.backend.features import FeatureResolver
from ezrules.backend.rule_executors.executors import LocalRuleExecutorSQL
from ezrules.backend.tasks import app as celery_app
from ezrules.backend.tasks import backtest_rule_change, execute_backtest_rule_change
from ezrules.core.rule import Rule
from ezrules.core.rule_updater import RDBRuleEngineConfigProducer, RDBRuleManager
from ezrules.models.backend_core import EventVersion, FeatureDefinition, FeatureSnapshotResolution, Organisation
from ezrules.models.backend_core import Rule as RuleModel
from tests.canonical_helpers import _hash_payload, add_served_decision, ensure_allowed_outcomes


def _ensure_org(session) -> Organisation:
    org = session.query(Organisation).filter(Organisation.o_id == 1).first()
    if org is None:
        org = Organisation(o_id=1, name="Test Org")
        session.add(org)
        session.commit()
    ensure_allowed_outcomes(session, org_id=int(org.o_id), outcome_names=["HOLD", "PASS"])
    return org


def _add_event_version(
    session,
    *,
    org_id: int,
    transaction_id: str,
    effective_at: datetime,
    event_data: dict,
    observed_at: datetime | None = None,
    terminal_state: bool = False,
):
    latest = (
        session.query(EventVersion)
        .filter(EventVersion.o_id == org_id, EventVersion.transaction_id == transaction_id)
        .order_by(EventVersion.event_version.desc(), EventVersion.ev_id.desc())
        .first()
    )
    event_version = EventVersion(
        o_id=org_id,
        transaction_id=transaction_id,
        event_version=1 if latest is None else int(latest.event_version) + 1,
        effective_at=effective_at,
        observed_at=observed_at or effective_at,
        event_data=event_data,
        payload_hash=_hash_payload(event_data),
        terminal_state=terminal_state,
        supersedes_ev_id=None if latest is None else int(latest.ev_id),
    )
    session.add(event_version)
    return event_version


def _active_sum_feature(org_id: int) -> FeatureDefinition:
    return FeatureDefinition(
        o_id=org_id,
        name="Sender sent amount 24h",
        entity="sender",
        feature_name="sent_amount_sum_24h",
        entity_key="sender_id",
        aggregation_type="sum",
        source_field="amount",
        window_seconds=86400,
        filters=[],
        status="active",
    )


def test_compute_backtest_metrics_resolves_stats_as_of_record_time(session):
    org = _ensure_org(session)
    session.add(_active_sum_feature(int(org.o_id)))
    for transaction_id, effective_at, event_data in (
        ("prior-1", datetime(2026, 5, 5, 12, 0, tzinfo=UTC), {"sender_id": "S1", "amount": 60}),
        ("prior-2", datetime(2026, 5, 5, 13, 0, tzinfo=UTC), {"sender_id": "S1", "amount": 70}),
        ("future", datetime(2026, 5, 6, 13, 0, tzinfo=UTC), {"sender_id": "S1", "amount": 10000}),
    ):
        _add_event_version(
            session,
            org_id=int(org.o_id),
            transaction_id=transaction_id,
            effective_at=effective_at,
            event_data=event_data,
        )
    session.commit()

    payload = compute_backtest_metrics(
        stored_rule=Rule(rid="stored", logic="if $amount > 0:\n\treturn !PASS"),
        proposed_rule=Rule(rid="proposed", logic="if stat[sender.sent_amount_sum_24h] > 100:\n\treturn !HOLD"),
        test_records=[
            BacktestRecord(
                event_data={"sender_id": "S1", "amount": 5},
                as_of=datetime(2026, 5, 6, 12, 0, tzinfo=UTC),
            )
        ],
        configs=[],
        feature_resolver=FeatureResolver(session, int(org.o_id)),
    )

    assert payload["total_records"] == 1
    assert payload["stored_result"] == {"PASS": 1}
    assert payload["proposed_result"] == {"HOLD": 1}


def test_aggregate_features_use_current_transaction_version_as_of_observed_time(session):
    org = _ensure_org(session)
    session.add(_active_sum_feature(int(org.o_id)))
    effective_at = datetime(2026, 5, 5, 12, 0, tzinfo=UTC)
    _add_event_version(
        session,
        org_id=int(org.o_id),
        transaction_id="corrected-txn",
        effective_at=effective_at,
        observed_at=datetime(2026, 5, 5, 12, 1, tzinfo=UTC),
        event_data={"sender_id": "S1", "amount": 100},
    )
    _add_event_version(
        session,
        org_id=int(org.o_id),
        transaction_id="corrected-txn",
        effective_at=effective_at,
        observed_at=datetime(2026, 5, 5, 14, 0, tzinfo=UTC),
        event_data={"sender_id": "S1", "amount": 10},
    )
    session.commit()

    resolver = FeatureResolver(session, int(org.o_id))
    before_correction = resolver.resolve(
        {"sender_id": "S1", "amount": 1},
        datetime(2026, 5, 5, 13, 0, tzinfo=UTC),
        {"sender.sent_amount_sum_24h"},
    )
    after_correction = resolver.resolve(
        {"sender_id": "S1", "amount": 1},
        datetime(2026, 5, 5, 15, 0, tzinfo=UTC),
        {"sender.sent_amount_sum_24h"},
    )

    assert before_correction == {"sender.sent_amount_sum_24h": 100.0}
    assert after_correction == {"sender.sent_amount_sum_24h": 10.0}


def test_compute_backtest_metrics_skips_records_missing_entity_key_for_stats(session):
    org = _ensure_org(session)
    session.add(_active_sum_feature(int(org.o_id)))
    session.commit()

    payload = compute_backtest_metrics(
        stored_rule=Rule(rid="stored", logic="if $amount > 0:\n\treturn !PASS"),
        proposed_rule=Rule(rid="proposed", logic="if stat[sender.sent_amount_sum_24h] > 100:\n\treturn !HOLD"),
        test_records=[BacktestRecord(event_data={"amount": 5}, as_of=datetime(2026, 5, 6, 12, 0, tzinfo=UTC))],
        configs=[],
        feature_resolver=FeatureResolver(session, int(org.o_id)),
    )

    assert payload["total_records"] == 0
    assert payload["skipped_records"] == 1
    assert any("computed stats could not be resolved" in warning for warning in payload["warnings"])


def test_compute_backtest_metrics_requires_resolver_when_rules_reference_stats():
    with pytest.raises(ValueError, match="feature resolution was not configured"):
        compute_backtest_metrics(
            stored_rule=Rule(rid="stored", logic="if $amount > 0:\n\treturn !PASS"),
            proposed_rule=Rule(rid="proposed", logic="if stat[sender.sent_amount_sum_24h] > 100:\n\treturn !HOLD"),
            test_records=[BacktestRecord(event_data={"sender_id": "S1", "amount": 5})],
            configs=[],
        )


def test_backtest_task_resolves_stats_as_of_event_time(session):
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True

    org = _ensure_org(session)
    session.add(_active_sum_feature(int(org.o_id)))
    rule = RuleModel(
        rid="bt_feature_rule",
        logic="if $amount > 0:\n\treturn !PASS",
        description="Backtest baseline rule",
        o_id=org.o_id,
    )
    session.add(rule)
    for transaction_id, effective_at, event_data in (
        ("prior-1", datetime(2026, 5, 5, 12, 0, tzinfo=UTC), {"sender_id": "S1", "amount": 60}),
        ("prior-2", datetime(2026, 5, 5, 13, 0, tzinfo=UTC), {"sender_id": "S1", "amount": 70}),
        ("future", datetime(2026, 5, 6, 13, 0, tzinfo=UTC), {"sender_id": "S1", "amount": 10000}),
    ):
        _add_event_version(
            session,
            org_id=int(org.o_id),
            transaction_id=transaction_id,
            effective_at=effective_at,
            event_data=event_data,
        )
    add_served_decision(
        session,
        org_id=int(org.o_id),
        transaction_id="current",
        effective_at=int(datetime(2026, 5, 6, 12, 0, tzinfo=UTC).timestamp()),
        event_data={"sender_id": "S1", "amount": 5},
    )
    session.commit()

    result = backtest_rule_change(
        rule.r_id,
        "if stat[sender.sent_amount_sum_24h] > 100:\n\treturn !HOLD",
        int(org.o_id),
    )

    assert "error" not in result
    assert result["total_records"] == 1
    assert result["stored_result"] == {"PASS": 1}
    assert result["proposed_result"] == {"HOLD": 1}

    celery_app.conf.task_always_eager = False
    celery_app.conf.task_eager_propagates = False


def test_backtest_task_persists_feature_snapshot_summary(session):
    org = _ensure_org(session)
    session.add(_active_sum_feature(int(org.o_id)))
    rule = RuleModel(
        rid="bt_feature_trace_rule",
        logic="if $amount > 0:\n\treturn !PASS",
        description="Backtest baseline rule",
        o_id=org.o_id,
    )
    session.add(rule)
    _add_event_version(
        session,
        org_id=int(org.o_id),
        transaction_id="prior-trace",
        effective_at=datetime(2026, 5, 5, 12, 0, tzinfo=UTC),
        event_data={"sender_id": "S1", "amount": 60},
    )
    add_served_decision(
        session,
        org_id=int(org.o_id),
        transaction_id="current-trace",
        effective_at=int(datetime(2026, 5, 5, 13, 0, tzinfo=UTC).timestamp()),
        event_data={"sender_id": "S1", "amount": 5},
    )
    session.commit()

    result = execute_backtest_rule_change(
        int(rule.r_id),
        "if stat[sender.sent_amount_sum_24h] > 50:\n\treturn !HOLD",
        int(org.o_id),
        task_id="feature-trace-task",
    )

    assert result["feature_snapshots"][0]["stat_path"] == "sender.sent_amount_sum_24h"
    assert result["feature_snapshots"][0]["matched_event_count_min"] == 1
    assert result["feature_snapshots"][0]["resolution_status_counts"] == {"resolved": 1}
    trace = session.query(FeatureSnapshotResolution).filter_by(backtest_task_id="feature-trace-task").one()
    assert trace.backtest_record_index == 0
    assert trace.ed_id is None


def test_live_evaluation_persists_feature_snapshot_trace(session, live_api_key):
    org = _ensure_org(session)
    org_id = int(org.o_id)
    session.add(_active_sum_feature(org_id))
    session.add(
        RuleModel(
            logic="if stat[sender.sent_amount_sum_24h] > 50:\n\treturn !HOLD",
            description="Hold senders with prior volume",
            rid="BT_FEATURE_TRACE:001",
            o_id=org_id,
            r_id=9401,
        )
    )
    _add_event_version(
        session,
        org_id=org_id,
        transaction_id="prior-live-trace",
        effective_at=datetime(2026, 5, 5, 12, 0, tzinfo=UTC),
        event_data={"sender_id": "S1", "amount": 60},
    )
    session.commit()

    config_producer = RDBRuleEngineConfigProducer(db=session, o_id=org_id)
    config_producer.save_config(RDBRuleManager(db=session, o_id=org_id))
    evaluator_router._lre = LocalRuleExecutorSQL(db=session, o_id=org_id)

    with TestClient(app) as client:
        response = client.post(
            "/api/v2/evaluate",
            json={
                "transaction_id": "current-live-trace",
                "effective_at": "2026-05-05T13:00:00Z",
                "event_data": {"sender_id": "S1", "amount": 5},
            },
            headers={"X-API-Key": live_api_key},
        )

    evaluator_router._lre = None
    assert response.status_code == 200
    evaluation_id = response.json()["evaluation_id"]
    trace = session.query(FeatureSnapshotResolution).filter_by(ed_id=evaluation_id).one()
    assert trace.stat_path == "sender.sent_amount_sum_24h"
    assert trace.backtest_task_id is None
    assert trace.matched_event_count == 1
