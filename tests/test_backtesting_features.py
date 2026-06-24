"""Backtesting with point-in-time computed stat resolution."""

from datetime import UTC, datetime

import pytest

from ezrules.backend.backtesting import BacktestRecord, compute_backtest_metrics
from ezrules.backend.features import FeatureResolver
from ezrules.backend.tasks import app as celery_app
from ezrules.backend.tasks import backtest_rule_change
from ezrules.core.rule import Rule
from ezrules.models.backend_core import EventVersion, FeatureDefinition, Organisation
from ezrules.models.backend_core import Rule as RuleModel
from tests.canonical_helpers import _hash_payload, add_served_decision


def _ensure_org(session) -> Organisation:
    org = session.query(Organisation).filter(Organisation.o_id == 1).first()
    if org is None:
        org = Organisation(o_id=1, name="Test Org")
        session.add(org)
        session.commit()
    return org


def _add_event_version(session, *, org_id: int, transaction_id: str, effective_at: datetime, event_data: dict):
    session.add(
        EventVersion(
            o_id=org_id,
            transaction_id=transaction_id,
            event_version=1,
            effective_at=effective_at,
            observed_at=effective_at,
            event_data=event_data,
            payload_hash=_hash_payload(event_data),
        )
    )


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
