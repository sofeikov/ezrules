import json

import pytest
from flask import g

from ezrules.backend import ezruleapp
from ezrules.backend.forms import OutcomeForm, RuleForm
from ezrules.models.backend_core import AllowedOutcome, Organisation, Rule, RuleHistory


def test_can_load_root_page(logged_in_manager_client):
    rv = logged_in_manager_client.get("/", follow_redirects=True)
    assert rv.status_code == 200


def test_can_load_rule_creation(logged_in_manager_client):
    rv = logged_in_manager_client.get("/create_rule")
    rv.status_code == 200


def test_can_create_new_rule(session, logged_in_manager_client):
    # Obtain CSRF token from this get request
    logged_in_manager_client.get("/create_rule")

    # Prepare an actual form
    form = RuleForm()
    form.rid.data = "TEST:001"
    form.description.data = "test"
    form.logic.data = "return 'HOLD'"
    form.csrf_token.data = g.csrf_token

    # Post rule and validate it was created
    rv = logged_in_manager_client.post("/create_rule", data=form.data, follow_redirects=True)
    added_rule = session.query(Rule).one()
    assert added_rule.r_id == 1
    assert added_rule.description == "test"
    assert added_rule.rid == "TEST:001"
    assert added_rule.logic == "return 'HOLD'"
    assert rv.status_code == 200


def test_can_not_create_new_invalid_rule(session, logged_in_manager_client):
    # The test is based on not providing a correct csra token thus
    # failing to propvide a valid submit form
    # Prepare an actual form
    form = RuleForm()
    form.rid.data = "TEST:001"
    form.description.data = "test"
    form.logic.data = "return 'NO SUCH OUTCOME'"

    # Post rule and validate it was created
    rv = logged_in_manager_client.post("/create_rule", data=form.data, follow_redirects=True)
    # Still good response as we redirect to the same page
    assert rv.status_code == 200
    assert "Value NO SUCH OUTCOME is not allowed in rule outcome;" in rv.data.decode()
    assert len(session.query(Rule).all()) == 0


def test_cant_display_non_existing_rule(logged_in_manager_client):
    rv = logged_in_manager_client.get("/rule/999", follow_redirects=True)
    assert rv.status_code == 404


def test_can_post_rule_update(session, logged_in_manager_client):
    rule = Rule(
        rid="TEST:001",
        description="test",
        logic="return 'HOLD'",
        o_id=session.query(Organisation).one().o_id,
    )
    session.add(rule)
    session.commit()

    # Obtain CSRF token from this get request
    logged_in_manager_client.get(f"/rule/{rule.r_id}")

    # Prepare an actual form
    form = RuleForm()
    form.rid.data = "TEST:001"
    form.description.data = "test"
    form.logic.data = "return 'CANCEL'"
    form.csrf_token.data = g.csrf_token

    logged_in_manager_client.post(f"/rule/{rule.r_id}", data=form.data, follow_redirects=True)
    logged_in_manager_client.get(f"/rule/{rule.r_id}/1")

    # Make sure history object is created
    assert session.query(RuleHistory).one().version == 1


def test_cant_update_rule_with_invalid_config(session, logged_in_manager_client):
    rule = Rule(
        rid="TEST:001",
        description="test",
        logic="return 'HOLD'",
        o_id=session.query(Organisation).one().o_id,
    )
    session.add(rule)
    session.commit()

    logged_in_manager_client.get(f"/rule/{rule.r_id}")

    # Prepare an actual form
    form = RuleForm()
    form.rid.data = "TEST:001"
    form.description.data = "test"
    form.logic.data = "return 'NO SUCH OUTCOME'"
    form.csrf_token.data = g.csrf_token

    rv = logged_in_manager_client.post(f"/rule/{rule.r_id}", data=form.data, follow_redirects=True)
    assert "The rule changes have not been saved, because:" in rv.data.decode()


def test_can_verify_rule_and_extract_params(logged_in_manager_client):
    rv = logged_in_manager_client.post(
        "/verify_rule",
        json={"rule_source": "if $amount>100:\n\treturn 'HOLD'"},
        follow_redirects=True,
    )
    assert json.loads(rv.data.decode())["params"] == ["amount"]


def test_cant_verify_rule_and_extract_params(logged_in_manager_client):
    rv = logged_in_manager_client.post(
        "/verify_rule",
        json={"rule_source": "if$amount>100:\n\treturn 'HOLD'"},
        follow_redirects=True,
    )
    assert json.loads(rv.data.decode()) == {}


def test_ping(logged_in_manager_client):
    rv = logged_in_manager_client.get("/ping")
    assert rv.data.decode() == "OK"


def test_can_load_user_lists(logged_in_manager_client):
    rv = logged_in_manager_client.get("/management/lists")
    assert rv.status_code == 200


def test_can_load_outcomes_page(logged_in_manager_client):
    rv = logged_in_manager_client.get("/management/outcomes")
    assert rv.status_code == 200


def test_can_add_outcomes(logged_in_manager_client):
    logged_in_manager_client.get("/management/outcomes")

    form = OutcomeForm()
    form.outcome.data = "NEW_TEST_OUTCOME"
    form.csrf_token.data = g.csrf_token

    rv = logged_in_manager_client.post("/management/outcomes", data=form.data, follow_redirects=True)
    assert "NEW_TEST_OUTCOME" in ezruleapp.outcome_manager.get_allowed_outcomes()
    assert rv.status_code == 200


@pytest.mark.parametrize(
    ["rule_source", "expected_response", "test_json"],
    [
        (
            "if $amount > 100:\n\treturn 'HOLD'",
            {"reason": "ok", "rule_outcome": "HOLD", "status": "ok"},
            json.dumps({"amount": 900}),
        ),
        (
            "if $amount > 100:\n\treturn 'HOLD'",
            {
                "status": "error",
                "reason": "Example is malformed",
                "rule_outcome": None,
            },
            r"\INCORRECT JSON",
        ),
        (
            "if $amount > 100\n\treturn 'HOLD'",
            {
                "status": "error",
                "reason": "Rule source is invalid",
                "rule_outcome": None,
            },
            json.dumps({"amount": 900}),
        ),
    ],
)
def test_can_test_rule(logged_in_manager_client, rule_source, expected_response, test_json):
    rv = logged_in_manager_client.post(
        "/test_rule",
        json={
            "rule_source": rule_source,
            "test_json": test_json,
        },
        follow_redirects=True,
    )
    test_result = json.loads(rv.data.decode())
    assert test_result == expected_response


def test_can_load_timeline(session, logged_in_manager_client):
    rule = Rule(
        rid="TEST:001",
        description="test",
        logic="return 'HOLD'",
        o_id=session.query(Organisation).one().o_id,
    )
    session.add(rule)
    session.commit()

    # Make changes
    rule.description = "update"
    session.commit()

    rv = logged_in_manager_client.get(f"/rule/{rule.r_id}/timeline")
    rv.status_code == 200


def test_app_uses_database_outcome_manager(session):
    """Test that the app is configured to use DatabaseOutcome manager"""
    from ezrules.core.outcomes import DatabaseOutcome

    assert isinstance(ezruleapp.outcome_manager, DatabaseOutcome)
    assert ezruleapp.outcome_manager.o_id == session.query(Organisation).first().o_id


def test_database_outcome_manager_creates_default_outcomes_on_app_start(session):
    """Test that default outcomes are created when DatabaseOutcome is initialized"""
    # Trigger lazy initialization by accessing outcomes
    ezruleapp.outcome_manager.get_allowed_outcomes()

    org = session.query(Organisation).first()
    outcomes = session.query(AllowedOutcome).filter_by(o_id=org.o_id).all()
    outcome_names = [o.outcome_name for o in outcomes]

    # Should have the three default outcomes
    assert "RELEASE" in outcome_names
    assert "HOLD" in outcome_names
    assert "CANCEL" in outcome_names


def test_outcome_form_adds_to_database(session, logged_in_manager_client):
    """Test that adding outcomes through the web form persists to database"""
    org = session.query(Organisation).first()

    # Get CSRF token
    logged_in_manager_client.get("/management/outcomes")

    # Add outcome through form
    form = OutcomeForm()
    form.outcome.data = "APPROVE"
    form.csrf_token.data = g.csrf_token

    rv = logged_in_manager_client.post("/management/outcomes", data=form.data, follow_redirects=True)

    # Check that outcome was persisted to database
    outcomes = session.query(AllowedOutcome).filter_by(o_id=org.o_id, outcome_name="APPROVE").all()
    assert len(outcomes) == 1

    # Check that outcome is available through manager
    assert "APPROVE" in ezruleapp.outcome_manager.get_allowed_outcomes()
    assert rv.status_code == 200


def test_rule_validation_uses_database_outcomes(session, logged_in_manager_client):
    """Test that rule validation checks against database outcomes"""
    org = session.query(Organisation).first()

    # Add a custom outcome to the database
    new_outcome = AllowedOutcome(outcome_name="CUSTOM_OUTCOME", o_id=org.o_id)
    session.add(new_outcome)
    session.commit()

    # Invalidate cache to ensure fresh load
    ezruleapp.outcome_manager._cached_outcomes = None

    # Get CSRF token
    logged_in_manager_client.get("/create_rule")

    # Create rule that uses the custom outcome
    form = RuleForm()
    form.rid.data = "TEST:CUSTOM"
    form.description.data = "test custom outcome"
    form.logic.data = "return 'CUSTOM_OUTCOME'"
    form.csrf_token.data = g.csrf_token

    rv = logged_in_manager_client.post("/create_rule", data=form.data, follow_redirects=True)

    # Rule should be created successfully since CUSTOM_OUTCOME is in database
    rule = session.query(Rule).filter_by(rid="TEST:CUSTOM").first()
    assert rule is not None
    assert rule.logic == "return 'CUSTOM_OUTCOME'"
    assert rv.status_code == 200


def test_can_load_audit_trail(logged_in_manager_client):
    rv = logged_in_manager_client.get("/audit")
    assert rv.status_code == 200


def test_can_load_user_management_page(logged_in_manager_client):
    rv = logged_in_manager_client.get("/management/users")
    assert rv.status_code == 200
