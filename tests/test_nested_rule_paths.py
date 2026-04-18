import pytest

from ezrules.backend.api_v2.routes.rules import test_rule as route_test_rule
from ezrules.backend.api_v2.routes.rules import verify_rule
from ezrules.backend.api_v2.schemas.rules import RuleTestRequest, RuleVerifyRequest
from ezrules.core.rule import MissingFieldLookupError, Rule
from ezrules.models.backend_core import FieldObservation
from tests.test_rules_verify_warnings import _build_rules_client


def test_rule_executes_nested_dollar_lookup_and_extracts_canonical_path():
    rule = Rule(rid="nested_lookup", logic="return $customer.profile.age >= 21")

    assert rule({"customer": {"profile": {"age": 34}}}) is True
    assert rule.get_rule_params() == {"customer.profile.age"}


def test_rule_reports_missing_nested_lookup_with_full_path():
    rule = Rule(rid="nested_missing", logic="return $customer.profile.age >= 21")

    with pytest.raises(MissingFieldLookupError, match="customer.profile.age"):
        rule({"customer": {"profile": {}}})


def test_verify_rule_returns_nested_params_and_suppresses_warning_for_observed_path(session):
    client = _build_rules_client(session)
    org = client.test_data["org"]  # type: ignore[attr-defined]

    session.add(FieldObservation(field_name="customer.profile.age", observed_json_type="int", o_id=org.o_id))
    session.commit()

    payload = verify_rule(
        RuleVerifyRequest(rule_source="return $customer.profile.age >= 21"),
        user=None,
        _=None,
        current_org_id=int(org.o_id),
        db=session,
    )

    client.close()

    assert payload.valid is True
    assert payload.params == ["customer.profile.age"]
    assert payload.warnings == []


def test_rules_test_reports_missing_nested_lookup_with_full_path(session):
    client = _build_rules_client(session)

    payload = route_test_rule(
        RuleTestRequest(
            rule_source="return $customer.profile.age >= 21",
            test_json='{"customer":{"profile":{}}}',
        ),
        user=None,
        _=None,
        current_org_id=1,
        db=session,
    )

    client.close()

    assert payload.status == "error"
    assert "customer.profile.age" in str(payload.reason)
    assert "lookup failed" in str(payload.reason)
