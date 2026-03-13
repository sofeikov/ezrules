"""Tests for demo-oriented reset seed helpers and bombardment payloads."""

import importlib

from ezrules.cli import _ensure_rule_quality_pair
from ezrules.models.backend_core import AllowedOutcome, Label, Organisation, RuleQualityPair

bombard = importlib.import_module("scripts.bombard_evaluator")


def test_ensure_rule_quality_pair_creates_and_reactivates(session):
    org = session.query(Organisation).first()
    assert org is not None

    session.add(AllowedOutcome(outcome_name="RELEASE", severity_rank=1, o_id=org.o_id))
    session.add(Label(label="CHARGEBACK"))
    session.commit()

    created = _ensure_rule_quality_pair(
        session,
        o_id=org.o_id,
        outcome="RELEASE",
        label="CHARGEBACK",
        created_by="test-suite",
    )

    assert created is True
    pair = (
        session.query(RuleQualityPair)
        .filter(
            RuleQualityPair.o_id == org.o_id,
            RuleQualityPair.outcome == "RELEASE",
            RuleQualityPair.label == "CHARGEBACK",
        )
        .one()
    )
    assert pair.active is True
    assert pair.created_by == "test-suite"

    pair.active = False
    session.commit()

    reactivated = _ensure_rule_quality_pair(
        session,
        o_id=org.o_id,
        outcome="RELEASE",
        label="CHARGEBACK",
        created_by="test-suite",
    )

    assert reactivated is True
    refreshed = (
        session.query(RuleQualityPair)
        .filter(
            RuleQualityPair.o_id == org.o_id,
            RuleQualityPair.outcome == "RELEASE",
            RuleQualityPair.label == "CHARGEBACK",
        )
        .all()
    )
    assert len(refreshed) == 1
    assert refreshed[0].active is True


def test_build_bombard_events_uses_demo_rule_schema():
    events = bombard.build_bombard_events(3, start_index=40)

    assert len(events) == 3
    assert events[0]["event_id"].startswith("bombard_00000041_")
    assert events[1]["event_id"].startswith("bombard_00000042_")

    for event in events:
        assert isinstance(event["event_timestamp"], int)
        assert "amount" in event["event_data"]
        assert "txn_type" in event["event_data"]
        assert "merchant_category" in event["event_data"]
        assert "device_age_days" in event["event_data"]
        assert "send_country" not in event["event_data"]
