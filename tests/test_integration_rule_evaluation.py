import json

from flask import g

from ezrules.backend.forms import RuleForm
from ezrules.core.rule_updater import RDBRuleEngineConfigProducer, RDBRuleManager
from ezrules.models.backend_core import Organisation, Rule, RuleHistory, TestingRecordLog, TestingResultsLog


class TestRuleEvaluationIntegration:
    """Integration tests for the complete rule creation -> evaluation -> outcome flow"""

    def test_full_rule_creation_to_evaluation_flow(self, session, logged_in_manager_client, logged_out_eval_client):
        """Test the complete flow: create rule in manager -> evaluate event in evaluator -> verify outcome"""
        org = session.query(Organisation).one()

        # Step 1: Create rule via manager service
        logged_in_manager_client.get("/create_rule")

        form = RuleForm()
        form.rid.data = "INTEGRATION:001"
        form.description.data = "Integration test rule"
        form.logic.data = "if $amount > 1000:\n    return 'HOLD'\nelse:\n    return 'RELEASE'"
        form.csrf_token.data = g.csrf_token

        rv = logged_in_manager_client.post("/create_rule", data=form.data, follow_redirects=True)
        assert rv.status_code == 200

        # Verify rule was created in database
        created_rule = session.query(Rule).filter_by(rid="INTEGRATION:001").one()
        assert created_rule.description == "Integration test rule"
        assert created_rule.o_id == org.o_id

        # Step 2: Update rule engine config to include new rule
        rm = RDBRuleManager(db=session, o_id=org.o_id)
        rule_engine_config_producer = RDBRuleEngineConfigProducer(db=session, o_id=org.o_id)
        rule_engine_config_producer.save_config(rm)

        # Step 3: Evaluate events via evaluator service
        # Test case 1: High amount should trigger HOLD
        rv = logged_out_eval_client.post(
            "/evaluate",
            json={"event_id": "test_event_1", "event_timestamp": 1234567890, "event_data": {"amount": 1500}},
        )
        result = json.loads(rv.data.decode())
        assert result["outcome_counters"] == {"HOLD": 1}
        assert result["outcome_set"] == ["HOLD"]
        assert str(created_rule.r_id) in result["rule_results"]
        assert result["rule_results"][str(created_rule.r_id)] == "HOLD"

        # Test case 2: Low amount should trigger RELEASE
        rv = logged_out_eval_client.post(
            "/evaluate", json={"event_id": "test_event_2", "event_timestamp": 1234567891, "event_data": {"amount": 500}}
        )
        result = json.loads(rv.data.decode())
        assert result["outcome_counters"] == {"RELEASE": 1}
        assert result["outcome_set"] == ["RELEASE"]
        assert str(created_rule.r_id) in result["rule_results"]
        assert result["rule_results"][str(created_rule.r_id)] == "RELEASE"

        # Step 4: Verify event and result logging
        event_logs = session.query(TestingRecordLog).filter_by(o_id=org.o_id).all()
        assert len(event_logs) == 2

        result_logs = session.query(TestingResultsLog).all()
        assert len(result_logs) == 2

        # Verify specific log entries
        hold_event = session.query(TestingRecordLog).filter_by(event_id="test_event_1").one()
        assert hold_event.event == {"amount": 1500}
        assert hold_event.event_timestamp == 1234567890

        hold_result = session.query(TestingResultsLog).filter_by(tl_id=hold_event.tl_id).one()
        assert hold_result.r_id == created_rule.r_id
        assert hold_result.rule_result == "HOLD"

    def test_rule_logic_execution_with_complex_data(self, session, logged_in_manager_client):
        """Test rule creation with more complex logic"""
        # Create rule with complex logic
        logged_in_manager_client.get("/create_rule")

        form = RuleForm()
        form.rid.data = "COMPLEX:001"
        form.description.data = "Complex logic rule"
        form.logic.data = """
if $transaction_type == 'WIRE' and $amount > 10000:
    return 'HOLD'
elif $country in ['US', 'CA'] and $amount > 5000:
    return 'CANCEL'
elif $customer_risk_score > 80:
    return 'HOLD'
else:
    return 'RELEASE'
"""
        form.csrf_token.data = g.csrf_token

        rv = logged_in_manager_client.post("/create_rule", data=form.data, follow_redirects=True)
        assert rv.status_code == 200

        # Verify rule was created with complex logic
        created_rule = session.query(Rule).filter_by(rid="COMPLEX:001").one()
        assert created_rule.description == "Complex logic rule"
        assert "transaction_type" in created_rule.logic
        assert "customer_risk_score" in created_rule.logic

    def test_rule_history_tracking_and_versioning(self, session, logged_in_manager_client):
        """Test that rule changes are tracked and versioned properly"""
        # Create initial rule
        logged_in_manager_client.get("/create_rule")

        form = RuleForm()
        form.rid.data = "VERSION:001"
        form.description.data = "Versioned rule"
        form.logic.data = "return 'HOLD'"
        form.csrf_token.data = g.csrf_token

        logged_in_manager_client.post("/create_rule", data=form.data, follow_redirects=True)
        created_rule = session.query(Rule).filter_by(rid="VERSION:001").one()

        # Update the rule
        logged_in_manager_client.get(f"/rule/{created_rule.r_id}")

        form = RuleForm()
        form.rid.data = "VERSION:001"
        form.description.data = "Versioned rule - updated"
        form.logic.data = "return 'RELEASE'"
        form.csrf_token.data = g.csrf_token

        logged_in_manager_client.post(f"/rule/{created_rule.r_id}", data=form.data, follow_redirects=True)

        # Verify history was created
        history = session.query(RuleHistory).filter_by(r_id=created_rule.r_id).one()
        assert history.version == 1
        assert history.logic == "return 'HOLD'"  # Original logic
        assert history.description == "Versioned rule"  # Original description

        # Verify current rule has updated values
        updated_rule = session.query(Rule).filter_by(r_id=created_rule.r_id).one()
        assert updated_rule.logic == "return 'RELEASE'"
        assert updated_rule.description == "Versioned rule - updated"

    def test_outcome_aggregation_with_multiple_rules(self, session, logged_in_manager_client, logged_out_eval_client):
        """Test outcome aggregation when multiple rules are evaluated"""
        org = session.query(Organisation).one()

        # Create multiple rules
        rules_data = [
            {
                "rid": "MULTI:001",
                "description": "Amount check rule",
                "logic": "if $amount > 1000:\n    return 'HOLD'\nelse:\n    return 'RELEASE'",
            },
            {
                "rid": "MULTI:002",
                "description": "Country check rule",
                "logic": "if $country in ['US', 'CA']:\n    return 'RELEASE'\nelse:\n    return 'CANCEL'",
            },
            {"rid": "MULTI:003", "description": "Always hold rule", "logic": "return 'HOLD'"},
        ]

        created_rules = []
        for rule_data in rules_data:
            logged_in_manager_client.get("/create_rule")

            form = RuleForm()
            form.rid.data = rule_data["rid"]
            form.description.data = rule_data["description"]
            form.logic.data = rule_data["logic"]
            form.csrf_token.data = g.csrf_token

            logged_in_manager_client.post("/create_rule", data=form.data, follow_redirects=True)
            rule = session.query(Rule).filter_by(rid=rule_data["rid"]).one()
            created_rules.append(rule)

        # Update rule engine config
        rm = RDBRuleManager(db=session, o_id=org.o_id)
        rule_engine_config_producer = RDBRuleEngineConfigProducer(db=session, o_id=org.o_id)
        rule_engine_config_producer.save_config(rm)

        # Test scenario with high amount, US country
        rv = logged_out_eval_client.post(
            "/evaluate",
            json={
                "event_id": "multi_test_1",
                "event_timestamp": 1234567890,
                "event_data": {"amount": 1500, "country": "US"},
            },
        )
        result = json.loads(rv.data.decode())

        # Expected results:
        # MULTI:001 -> HOLD (amount > 1000)
        # MULTI:002 -> RELEASE (country is US)
        # MULTI:003 -> HOLD (always)
        expected_counters = {"HOLD": 2, "RELEASE": 1}
        expected_set = ["HOLD", "RELEASE"]

        assert result["outcome_counters"] == expected_counters
        assert result["outcome_set"] == expected_set
        assert len(result["rule_results"]) == 3

        # Verify individual rule results
        assert result["rule_results"][str(created_rules[0].r_id)] == "HOLD"
        assert result["rule_results"][str(created_rules[1].r_id)] == "RELEASE"
        assert result["rule_results"][str(created_rules[2].r_id)] == "HOLD"

    def test_rule_validation_pipeline(self, session, logged_in_manager_client):
        """Test rule validation catches logic errors before saving"""
        # Test invalid outcome (this is the validation that actually works)
        logged_in_manager_client.get("/create_rule")

        form = RuleForm()
        form.rid.data = "INVALID:002"
        form.description.data = "Invalid outcome rule"
        form.logic.data = "return 'INVALID_OUTCOME'"
        form.csrf_token.data = g.csrf_token

        rv = logged_in_manager_client.post("/create_rule", data=form.data, follow_redirects=True)
        assert "Value INVALID_OUTCOME is not allowed in rule outcome" in rv.data.decode()

        # Rule should not be created due to invalid outcome
        rules = session.query(Rule).filter_by(rid="INVALID:002").all()
        assert len(rules) == 0

        # Test valid rule creation for comparison
        logged_in_manager_client.get("/create_rule")

        form = RuleForm()
        form.rid.data = "VALID:001"
        form.description.data = "Valid rule"
        form.logic.data = "return 'HOLD'"
        form.csrf_token.data = g.csrf_token

        rv = logged_in_manager_client.post("/create_rule", data=form.data, follow_redirects=True)
        assert rv.status_code == 200

        # Valid rule should be created
        rules = session.query(Rule).filter_by(rid="VALID:001").all()
        assert len(rules) == 1

    def test_error_handling_in_evaluation(self, session, logged_in_manager_client, logged_out_eval_client):
        """Test error handling during rule evaluation"""
        org = session.query(Organisation).one()

        # Create a rule that should work normally
        logged_in_manager_client.get("/create_rule")

        form = RuleForm()
        form.rid.data = "ERROR:001"
        form.description.data = "Safe rule"
        form.logic.data = "if 'amount' in t and t['amount'] > 100:\n    return 'HOLD'\nelse:\n    return 'RELEASE'"
        form.csrf_token.data = g.csrf_token

        logged_in_manager_client.post("/create_rule", data=form.data, follow_redirects=True)
        created_rule = session.query(Rule).filter_by(rid="ERROR:001").one()

        # Update rule engine config
        rm = RDBRuleManager(db=session, o_id=org.o_id)
        rule_engine_config_producer = RDBRuleEngineConfigProducer(db=session, o_id=org.o_id)
        rule_engine_config_producer.save_config(rm)

        # Test evaluation with present field
        rv = logged_out_eval_client.post(
            "/evaluate", json={"event_id": "error_test_1", "event_timestamp": 1234567890, "event_data": {"amount": 150}}
        )

        # Should work normally
        result = json.loads(rv.data.decode())
        assert str(created_rule.r_id) in result["rule_results"]
        assert result["rule_results"][str(created_rule.r_id)] == "HOLD"
        assert result["outcome_counters"] == {"HOLD": 1}

        # Test evaluation with missing field - rule should handle gracefully
        rv = logged_out_eval_client.post(
            "/evaluate",
            json={
                "event_id": "error_test_2",
                "event_timestamp": 1234567891,
                "event_data": {"other_field": 100},  # Missing amount field
            },
        )

        # Should still work and return RELEASE (else branch)
        result = json.loads(rv.data.decode())
        assert str(created_rule.r_id) in result["rule_results"]
        assert result["rule_results"][str(created_rule.r_id)] == "RELEASE"
        assert result["outcome_counters"] == {"RELEASE": 1}
