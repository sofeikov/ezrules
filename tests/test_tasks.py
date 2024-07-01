from ezrules.backend.tasks import count_rule_outcomes
from ezrules.models.backend_core import TestingRecordLog
from ezrules.core.rule import Rule


def test_collect_trivial_outcome():
    r = Rule(logic="return 'HOLD'", rid="1")
    l = [
        TestingRecordLog(event={}, event_timestamp=1, event_id="1"),
        TestingRecordLog(event={}, event_timestamp=2, event_id="2"),
    ]

    outcomes = count_rule_outcomes(r, l)
    assert outcomes == {"HOLD": len(l)}


def test_collect_half_outcome():
    r = Rule(logic="if $amount>500:\n\t return 'HOLD'", rid="1")
    l = [
        TestingRecordLog(event={"amount": 600}, event_timestamp=1, event_id="1"),
        TestingRecordLog(event={"amount": 300}, event_timestamp=2, event_id="2"),
    ]

    outcomes = count_rule_outcomes(r, l)
    assert outcomes == {"HOLD": 1}