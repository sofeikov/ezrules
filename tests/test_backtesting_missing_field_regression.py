from ezrules.backend.tasks import backtest_rule_change
from ezrules.models.backend_core import Organisation, TestingRecordLog
from ezrules.models.backend_core import Rule as RuleModel


def test_backtest_skips_records_when_proposed_score_field_never_appeared_in_history(session):
    org = session.query(Organisation).filter(Organisation.o_id == 1).one()
    rule = RuleModel(
        rid="BT_SCORE_REGRESSION_001",
        logic='if $amount > 100:\n\treturn "HOLD"',
        description="Backtest regression coverage for unseen score field",
        o_id=int(org.o_id),
    )
    session.add(rule)
    session.add_all(
        [
            TestingRecordLog(
                event={"amount": 150},
                event_timestamp=1700000001,
                event_id="score-regression-1",
                o_id=int(org.o_id),
            ),
            TestingRecordLog(
                event={"amount": 75},
                event_timestamp=1700000002,
                event_id="score-regression-2",
                o_id=int(org.o_id),
            ),
        ]
    )
    session.commit()

    result = backtest_rule_change(
        int(rule.r_id),
        'if $score > 100:\n\treturn "HOLD"',
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
