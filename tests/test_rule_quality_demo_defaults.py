"""Tests for demo rule-quality defaults and ranking behavior."""

import datetime

from ezrules.backend.rule_quality import compute_rule_quality_metrics
from ezrules.cli import DEFAULT_DEMO_RULE_QUALITY_PAIRS, _ensure_default_rule_quality_pairs
from ezrules.models.backend_core import (
    AllowedOutcome,
    Label,
    Organisation,
    RuleQualityPair,
)
from ezrules.models.backend_core import Rule as RuleModel
from tests.canonical_helpers import add_served_decision


def test_ensure_default_rule_quality_pairs_seeds_demo_ready_pairs(session):
    org = session.query(Organisation).first()
    assert org is not None

    session.add_all(
        [
            AllowedOutcome(outcome_name="RELEASE", severity_rank=1, o_id=org.o_id),
            AllowedOutcome(outcome_name="HOLD", severity_rank=2, o_id=org.o_id),
            AllowedOutcome(outcome_name="CANCEL", severity_rank=3, o_id=org.o_id),
            Label(label="CHARGEBACK"),
            Label(label="FRAUD"),
        ]
    )
    session.commit()

    seeded_pairs = _ensure_default_rule_quality_pairs(
        session,
        o_id=org.o_id,
        created_by="test-suite",
    )

    assert seeded_pairs == list(DEFAULT_DEMO_RULE_QUALITY_PAIRS)

    stored_pairs = {
        (pair.outcome, pair.label, pair.active, pair.created_by)
        for pair in session.query(RuleQualityPair).filter(RuleQualityPair.o_id == org.o_id).all()
    }
    assert stored_pairs == {
        ("RELEASE", "CHARGEBACK", True, "test-suite"),
        ("HOLD", "CHARGEBACK", True, "test-suite"),
        ("CANCEL", "FRAUD", True, "test-suite"),
    }


def test_compute_rule_quality_metrics_excludes_unscored_rules_from_rankings(session):
    org = session.query(Organisation).first()
    assert org is not None

    rule = RuleModel(
        rid="quality_unscored_rule",
        logic="return !HOLD",
        description="Rule with zero predicted positives for the curated pair",
        o_id=org.o_id,
    )
    label = Label(label="CHARGEBACK")
    session.add_all([rule, label])
    session.commit()

    created_at = datetime.datetime.now()
    decision = add_served_decision(
        session,
        org_id=int(org.o_id),
        event_id="quality_unscored_event",
        event_data={"amount": 100},
        event_timestamp=int(created_at.timestamp()),
        evaluated_at=created_at,
        rule_results={int(rule.r_id): "HOLD"},
        label=label,
    )
    session.commit()

    payload = compute_rule_quality_metrics(
        session,
        min_support=1,
        lookback_days=30,
        freeze_at=created_at + datetime.timedelta(minutes=1),
        max_decision_id=decision.ed_id,
        o_id=org.o_id,
        curated_pairs=[("RELEASE", "CHARGEBACK")],
    )

    assert len(payload["pair_metrics"]) == 1
    assert payload["pair_metrics"][0]["predicted_positives"] == 0
    assert payload["pair_metrics"][0]["actual_positives"] == 1
    assert payload["pair_metrics"][0]["f1"] is None
    assert payload["best_rules"] == []
    assert payload["worst_rules"] == []
