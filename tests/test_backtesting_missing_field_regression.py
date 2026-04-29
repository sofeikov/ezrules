from ezrules.backend.tasks import backtest_rule_change
from ezrules.models.backend_core import Organisation
from ezrules.models.backend_core import Rule as RuleModel
from tests.canonical_helpers import add_served_decision


def test_backtest_skips_records_when_proposed_score_field_never_appeared_in_history(session):
    org = session.query(Organisation).filter(Organisation.o_id == 1).one()
    rule = RuleModel(
        rid="BT_SCORE_REGRESSION_001",
        logic="if $amount > 100:\n\treturn !HOLD",
        description="Backtest regression coverage for unseen score field",
        o_id=int(org.o_id),
    )
    session.add(rule)
    add_served_decision(
        session,
        org_id=int(org.o_id),
        event_id="score-regression-1",
        event_timestamp=1700000001,
        event_data={"amount": 150},
    )
    add_served_decision(
        session,
        org_id=int(org.o_id),
        event_id="score-regression-2",
        event_timestamp=1700000002,
        event_data={"amount": 75},
    )
    session.commit()

    result = backtest_rule_change(
        int(rule.r_id),
        "if $score > 100:\n\treturn !HOLD",
        int(org.o_id),
    )

    assert "error" not in result
    assert result["total_records"] == 0
    assert result["eligible_records"] == 0
    assert result["skipped_records"] == 2
    assert result["stored_result"] == {}
    assert result["proposed_result"] == {}
    assert any("Skipped 2 historical record(s)" in warning for warning in result["warnings"])
    assert any("score (2)" in warning for warning in result["warnings"])
