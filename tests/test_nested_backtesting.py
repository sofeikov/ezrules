from ezrules.backend.backtesting import BacktestRecord, compute_backtest_metrics
from ezrules.core.rule import Rule
from ezrules.core.type_casting import FieldCastConfig, FieldType
from ezrules.models.backend_core import Organisation


def _ensure_org(session) -> Organisation:
    org = session.query(Organisation).filter(Organisation.o_id == 1).first()
    if org is None:
        org = Organisation(o_id=1, name="Test Org")
        session.add(org)
        session.commit()
    return org


def test_backtesting_normalizes_nested_paths_and_reports_missing_nested_fields(session):
    org = _ensure_org(session)
    payload = compute_backtest_metrics(
        stored_rule=Rule(rid="stored_nested", logic="if $customer.profile.age >= 21:\n\treturn !HOLD"),
        proposed_rule=Rule(rid="proposed_nested", logic="if $customer.profile.age >= 30:\n\treturn !REVIEW"),
        test_records=[
            BacktestRecord(event_data={"customer": {"profile": {"age": "34"}}}),
            BacktestRecord(event_data={"customer": {"profile": {}}}),
        ],
        configs=[FieldCastConfig(field_name="customer.profile.age", field_type=FieldType.INTEGER)],
    )

    assert payload["eligible_records"] == 1
    assert payload["skipped_records"] == 1
    assert payload["stored_result"] == {"HOLD": 1}
    assert payload["proposed_result"] == {"REVIEW": 1}
    assert any("customer.profile.age (1)" in warning for warning in payload["warnings"])
