import datetime

import pytest
from fastapi.testclient import TestClient

from ezrules.backend.api_v2.main import app
from ezrules.backend.api_v2.routes import evaluator as evaluator_router
from ezrules.backend.rule_quality import compute_rule_quality_metrics
from ezrules.core.rule_updater import RDBRuleEngineConfigProducer, RDBRuleManager
from ezrules.models.backend_core import AllowedOutcome, EventVersionLabel, Label, Organisation, RuleQualityPair
from ezrules.models.backend_core import Rule as RuleModel
from tests.canonical_helpers import add_served_decision


def test_non_firing_labeled_event_counts_as_false_negative(session, live_api_key):
    """Every labeled event belongs in the rule's confusion-matrix universe."""
    org = session.query(Organisation).filter(Organisation.o_id == 1).one()
    rule = RuleModel(
        rid="quality_confusion_matrix_contract",
        logic="if $amount > 100:\n\treturn !HOLD",
        description="Hold high-value events",
        o_id=int(org.o_id),
    )
    fraud = Label(label="FRAUD", o_id=int(org.o_id))
    normal = Label(label="NORMAL", o_id=int(org.o_id))
    session.add_all(
        [
            rule,
            fraud,
            normal,
            AllowedOutcome(outcome_name="HOLD", severity_rank=1, o_id=int(org.o_id)),
        ]
    )
    session.flush()
    session.add(
        RuleQualityPair(
            outcome="HOLD",
            label="FRAUD",
            active=True,
            created_by="confusion-matrix-contract",
            o_id=int(org.o_id),
        )
    )

    session.commit()
    RDBRuleEngineConfigProducer(db=session, o_id=int(org.o_id)).save_config(
        RDBRuleManager(db=session, o_id=int(org.o_id))
    )

    now = datetime.datetime.now(datetime.UTC)
    examples = [
        # A: fires and is FRAUD (true positive).
        ("quality-contract-a", 150, fraud),
        # B: does not fire and is FRAUD (false negative).
        ("quality-contract-b", 50, fraud),
        # C: fires and is NORMAL (false positive).
        ("quality-contract-c", 160, normal),
        # D: does not fire and is NORMAL (true negative).
        ("quality-contract-d", 40, normal),
    ]
    evaluator_router._lre = None
    evaluator_router._shadow_lre = None
    evaluator_router._allowlist_lre = None
    try:
        with TestClient(app) as client:
            for offset, (transaction_id, amount, label) in enumerate(examples):
                response = client.post(
                    "/api/v2/evaluate",
                    json={
                        "transaction_id": transaction_id,
                        "effective_at": int((now + datetime.timedelta(seconds=offset)).timestamp()),
                        "event_data": {"amount": amount},
                    },
                    headers={"X-API-Key": live_api_key},
                )
                assert response.status_code == 200
                session.add(
                    EventVersionLabel(
                        o_id=int(org.o_id),
                        ev_id=int(response.json()["event_version_id"]),
                        el_id=int(label.el_id),
                        assigned_by="confusion-matrix-contract",
                    )
                )
                session.commit()
    finally:
        evaluator_router._lre = None
        evaluator_router._shadow_lre = None
        evaluator_router._allowlist_lre = None

    freeze_at = now + datetime.timedelta(minutes=1)
    result = compute_rule_quality_metrics(
        session,
        min_support=1,
        lookback_days=1,
        freeze_at=freeze_at,
        max_decision_id=None,
        o_id=int(org.o_id),
        curated_pairs=[("HOLD", "FRAUD")],
    )

    assert result["total_labeled_events"] == 4
    assert len(result["pair_metrics"]) == 1
    metric = result["pair_metrics"][0]
    assert metric["rid"] == rule.rid
    assert metric["true_positive"] == 1
    assert metric["false_positive"] == 1
    assert metric["false_negative"] == 1
    assert metric["predicted_positives"] == 2
    assert metric["actual_positives"] == 2
    assert metric["precision"] == pytest.approx(0.5)
    assert metric["recall"] == pytest.approx(0.5)
    assert metric["f1"] == pytest.approx(0.5)

    assert result["best_rules"][0]["labeled_events"] == 4
    assert result["worst_rules"][0]["labeled_events"] == 4


def test_rule_quality_denominator_includes_only_events_where_rule_was_evaluated(session):
    """A first-match-skipped rule is absent, while an evaluated no-fire rule is a false negative."""
    org = session.query(Organisation).filter(Organisation.o_id == 1).one()
    first_rule = RuleModel(rid="quality_first", logic="return !HOLD", description="First rule", o_id=int(org.o_id))
    later_rule = RuleModel(rid="quality_later", logic="return !HOLD", description="Later rule", o_id=int(org.o_id))
    fraud = Label(label="FRAUD", o_id=int(org.o_id))
    session.add_all([first_rule, later_rule, fraud])
    session.flush()

    now = datetime.datetime.now(datetime.UTC)
    first_decision = add_served_decision(
        session,
        org_id=int(org.o_id),
        transaction_id="quality-first-match-stopped",
        event_data={"amount": 150},
        evaluated_at=now,
        rule_results={int(first_rule.r_id): "HOLD"},
        label=fraud,
    )
    first_decision.all_rule_results = {str(int(first_rule.r_id)): "HOLD"}

    second_decision = add_served_decision(
        session,
        org_id=int(org.o_id),
        transaction_id="quality-all-rules-no-fire",
        event_data={"amount": 50},
        evaluated_at=now + datetime.timedelta(seconds=1),
        label=fraud,
    )
    second_decision.all_rule_results = {
        str(int(first_rule.r_id)): None,
        str(int(later_rule.r_id)): None,
    }

    legacy_decision = add_served_decision(
        session,
        org_id=int(org.o_id),
        transaction_id="quality-missing-exposure-snapshot",
        event_data={"amount": 75},
        evaluated_at=now + datetime.timedelta(seconds=2),
        label=fraud,
    )
    legacy_decision.all_rule_results = None
    session.commit()

    result = compute_rule_quality_metrics(
        session,
        min_support=1,
        lookback_days=1,
        freeze_at=now + datetime.timedelta(minutes=1),
        max_decision_id=None,
        o_id=int(org.o_id),
        curated_pairs=[("HOLD", "FRAUD")],
    )
    metrics = {metric["rid"]: metric for metric in result["pair_metrics"]}

    assert result["total_labeled_events"] == 2
    assert metrics[first_rule.rid]["actual_positives"] == 2
    assert metrics[first_rule.rid]["false_negative"] == 1

    assert metrics[later_rule.rid]["actual_positives"] == 1
    assert metrics[later_rule.rid]["predicted_positives"] == 0
    assert metrics[later_rule.rid]["false_negative"] == 1
    assert metrics[later_rule.rid]["precision"] is None
    assert metrics[later_rule.rid]["recall"] == pytest.approx(0.0)
    assert metrics[later_rule.rid]["f1"] is None

    summaries = {summary["rid"]: summary for summary in result["best_rules"] + result["worst_rules"]}
    assert summaries[first_rule.rid]["labeled_events"] == 2
    assert later_rule.rid not in summaries
