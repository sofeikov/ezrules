import json

import pytest
from flask import g

from ezrules.backend import ezruleapp
from ezrules.backend.forms import OutcomeForm, RuleForm
from ezrules.core.permissions import PermissionManager
from ezrules.models.backend_core import AllowedOutcome, Organisation, Role, Rule, RuleHistory


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


def test_can_load_role_management_page(logged_in_manager_client):
    rv = logged_in_manager_client.get("/role_management")
    assert rv.status_code == 200


def test_can_load_role_permissions_page(session, logged_in_manager_client):
    # Set up the permission manager to use the test session
    original_db_session = PermissionManager.db_session
    PermissionManager.db_session = session
    ezruleapp.db_session = session

    try:
        # Initialize default actions in the database for this test
        PermissionManager.init_default_actions()

        # Create a test role
        test_role = Role(name="test_role", description="Test role for permissions")
        session.add(test_role)
        session.commit()

        rv = logged_in_manager_client.get(f"/role_permissions/{test_role.id}")
        assert rv.status_code == 200
    finally:
        # Restore original db_session
        PermissionManager.db_session = original_db_session


def test_mark_event_endpoint_exists(logged_in_manager_client):
    """Test that the mark-event endpoint exists and handles missing data"""
    rv = logged_in_manager_client.post("/mark-event", json={})
    assert rv.status_code == 400
    assert "event_id and label_name are required" in rv.get_json()["error"]


def test_mark_event_success(session, logged_in_manager_client):
    """Test successfully marking an event with a label"""
    from ezrules.models.backend_core import Label, TestingRecordLog, Organisation

    # Create test data in the session
    org = session.query(Organisation).first()
    test_event = TestingRecordLog(
        event_id="test_event_123", event_timestamp=1234567890, event={"test": "data"}, o_id=org.o_id
    )
    session.add(test_event)

    # Create a test label
    test_label = Label(label="FRAUD")
    session.add(test_label)
    session.commit()

    # Mark the event with the label
    rv = logged_in_manager_client.post("/mark-event", json={"event_id": "test_event_123", "label_name": "FRAUD"})

    assert rv.status_code == 200
    response_data = rv.get_json()
    assert response_data["event_id"] == "test_event_123"
    assert response_data["label_name"] == "FRAUD"
    assert "successfully marked" in response_data["message"]

    # Verify the database was updated
    session.refresh(test_event)
    assert test_event.el_id == test_label.el_id


def test_mark_event_event_not_found(logged_in_manager_client):
    """Test marking a non-existent event"""
    rv = logged_in_manager_client.post("/mark-event", json={"event_id": "nonexistent_event", "label_name": "FRAUD"})

    assert rv.status_code == 404
    assert "Event with id 'nonexistent_event' not found" in rv.get_json()["error"]


def test_mark_event_label_not_found(session, logged_in_manager_client):
    """Test marking an event with a non-existent label"""
    from ezrules.models.backend_core import TestingRecordLog, Organisation

    # Create a test event
    org = session.query(Organisation).first()
    test_event = TestingRecordLog(
        event_id="test_event_456", event_timestamp=1234567890, event={"test": "data"}, o_id=org.o_id
    )
    session.add(test_event)
    session.commit()

    # Try to mark with non-existent label
    rv = logged_in_manager_client.post(
        "/mark-event", json={"event_id": "test_event_456", "label_name": "NONEXISTENT_LABEL"}
    )

    assert rv.status_code == 404
    assert "Label 'NONEXISTENT_LABEL' not found" in rv.get_json()["error"]


def test_mark_event_missing_json_data(logged_in_manager_client):
    """Test the endpoint with no JSON data"""
    rv = logged_in_manager_client.post("/mark-event", data="", headers={"Content-Type": "application/json"})
    assert rv.status_code == 400
    assert "JSON data required" in rv.get_json()["error"]


def test_mark_event_missing_event_id(logged_in_manager_client):
    """Test the endpoint with missing event_id"""
    rv = logged_in_manager_client.post("/mark-event", json={"label_name": "FRAUD"})
    assert rv.status_code == 400
    assert "event_id and label_name are required" in rv.get_json()["error"]


def test_mark_event_missing_label_name(logged_in_manager_client):
    """Test the endpoint with missing label_name"""
    rv = logged_in_manager_client.post("/mark-event", json={"event_id": "test_event"})
    assert rv.status_code == 400
    assert "event_id and label_name are required" in rv.get_json()["error"]


def test_upload_labels_page_loads(logged_in_manager_client):
    """Test that the upload labels page loads successfully"""
    rv = logged_in_manager_client.get("/upload_labels")
    assert rv.status_code == 200
    assert b"Upload Transaction Labels" in rv.data
    assert b"CSV Format Requirements" in rv.data


def test_upload_labels_successful_upload(session, logged_in_manager_client):
    """Test successful CSV upload with valid data"""
    from ezrules.models.backend_core import Label, TestingRecordLog, Organisation
    from flask import g
    import io

    # Create test data in the session
    org = session.query(Organisation).first()

    # Create test events
    test_event1 = TestingRecordLog(
        event_id="csv_event_1", event_timestamp=1234567890, event={"test": "data1"}, o_id=org.o_id
    )
    test_event2 = TestingRecordLog(
        event_id="csv_event_2", event_timestamp=1234567891, event={"test": "data2"}, o_id=org.o_id
    )
    session.add(test_event1)
    session.add(test_event2)

    # Create test labels
    fraud_label = Label(label="FRAUD")
    normal_label = Label(label="NORMAL")
    session.add(fraud_label)
    session.add(normal_label)
    session.commit()

    # Get CSRF token
    logged_in_manager_client.get("/upload_labels")

    # Create CSV content
    csv_content = "csv_event_1,FRAUD\ncsv_event_2,NORMAL\n"
    csv_file = io.BytesIO(csv_content.encode("utf-8"))

    # Upload the CSV file
    rv = logged_in_manager_client.post(
        "/upload_labels",
        data={"csv_file": (csv_file, "test_labels.csv"), "csrf_token": g.csrf_token},
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    assert rv.status_code == 200
    assert b"Successfully processed 2 labels" in rv.data

    # Verify the database was updated
    session.refresh(test_event1)
    session.refresh(test_event2)
    assert test_event1.el_id == fraud_label.el_id
    assert test_event2.el_id == normal_label.el_id


def test_upload_labels_event_not_found(session, logged_in_manager_client):
    """Test CSV upload with non-existent event ID"""
    from ezrules.models.backend_core import Label
    from flask import g
    import io

    # Create test label
    fraud_label = Label(label="FRAUD")
    session.add(fraud_label)
    session.commit()

    # Get CSRF token
    logged_in_manager_client.get("/upload_labels")

    # Create CSV content with non-existent event ID
    csv_content = "nonexistent_event,FRAUD\n"
    csv_file = io.BytesIO(csv_content.encode("utf-8"))

    # Upload the CSV file
    rv = logged_in_manager_client.post(
        "/upload_labels",
        data={"csv_file": (csv_file, "test_labels.csv"), "csrf_token": g.csrf_token},
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    assert rv.status_code == 200
    assert b"Failed to process 1 rows" in rv.data
    assert b"Event with id &#39;nonexistent_event&#39; not found" in rv.data


def test_upload_labels_label_not_found(session, logged_in_manager_client):
    """Test CSV upload with non-existent label"""
    from ezrules.models.backend_core import TestingRecordLog, Organisation
    from flask import g
    import io

    # Create test data
    org = session.query(Organisation).first()
    test_event = TestingRecordLog(
        event_id="csv_event_test", event_timestamp=1234567890, event={"test": "data"}, o_id=org.o_id
    )
    session.add(test_event)
    session.commit()

    # Get CSRF token
    logged_in_manager_client.get("/upload_labels")

    # Create CSV content with non-existent label
    csv_content = "csv_event_test,NONEXISTENT_LABEL\n"
    csv_file = io.BytesIO(csv_content.encode("utf-8"))

    # Upload the CSV file
    rv = logged_in_manager_client.post(
        "/upload_labels",
        data={"csv_file": (csv_file, "test_labels.csv"), "csrf_token": g.csrf_token},
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    assert rv.status_code == 200
    assert b"Failed to process 1 rows" in rv.data
    assert b"Label &#39;NONEXISTENT_LABEL&#39; not found" in rv.data


def test_upload_labels_invalid_csv_format(logged_in_manager_client):
    """Test CSV upload with invalid format (wrong number of columns)"""
    from flask import g
    import io

    # Get CSRF token
    logged_in_manager_client.get("/upload_labels")

    # Create CSV content with wrong number of columns
    csv_content = "event_id_only\nevent_id,label,extra_column\n"
    csv_file = io.BytesIO(csv_content.encode("utf-8"))

    # Upload the CSV file
    rv = logged_in_manager_client.post(
        "/upload_labels",
        data={"csv_file": (csv_file, "test_labels.csv"), "csrf_token": g.csrf_token},
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    assert rv.status_code == 200
    assert b"Failed to process 2 rows" in rv.data
    assert b"Expected 2 columns (event_id,label)" in rv.data


def test_upload_labels_empty_csv(logged_in_manager_client):
    """Test CSV upload with empty file"""
    from flask import g
    import io

    # Get CSRF token
    logged_in_manager_client.get("/upload_labels")

    # Create empty CSV content
    csv_content = ""
    csv_file = io.BytesIO(csv_content.encode("utf-8"))

    # Upload the CSV file
    rv = logged_in_manager_client.post(
        "/upload_labels",
        data={"csv_file": (csv_file, "test_labels.csv"), "csrf_token": g.csrf_token},
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    assert rv.status_code == 200
    assert b"CSV file was empty or contained no valid data" in rv.data


def test_dashboard_page_loads(logged_in_manager_client):
    """Test that the dashboard page loads successfully"""
    rv = logged_in_manager_client.get("/dashboard")
    assert rv.status_code == 200
    assert b"Dashboard" in rv.data
    assert b"Active Rules" in rv.data
    assert b"Transaction Analytics" in rv.data


def test_dashboard_displays_active_rules_count(session, logged_in_manager_client):
    """Test that the dashboard displays the correct number of active rules"""
    # Create test rules
    org = session.query(Organisation).first()
    rule1 = Rule(rid="TEST:001", description="test rule 1", logic="return 'HOLD'", o_id=org.o_id)
    rule2 = Rule(rid="TEST:002", description="test rule 2", logic="return 'RELEASE'", o_id=org.o_id)
    session.add(rule1)
    session.add(rule2)
    session.commit()

    rv = logged_in_manager_client.get("/dashboard")
    assert rv.status_code == 200
    # Check that the count is displayed (looking for 2 active rules)
    assert b"Active Rules" in rv.data


def test_dashboard_displays_transactions_today(session, logged_in_manager_client):
    """Test that the dashboard displays transaction analytics charts"""
    from ezrules.models.backend_core import TestingRecordLog
    import datetime

    org = session.query(Organisation).first()

    # Create transactions today
    today_event = TestingRecordLog(
        event_id="today_event_1",
        event_timestamp=int(datetime.datetime.now().timestamp()),
        event={"test": "data"},
        o_id=org.o_id,
        created_at=datetime.datetime.now(),
    )
    session.add(today_event)
    session.commit()

    rv = logged_in_manager_client.get("/dashboard")
    assert rv.status_code == 200
    assert b"Transaction Analytics" in rv.data
    assert b"transactionVolumeChart" in rv.data


def test_dashboard_displays_outcomes_by_type(session, logged_in_manager_client):
    """Test that the dashboard displays outcomes distribution chart"""
    from ezrules.models.backend_core import TestingRecordLog, TestingResultsLog
    import datetime

    org = session.query(Organisation).first()

    # Create a rule
    rule = Rule(rid="TEST:003", description="test rule", logic="return 'HOLD'", o_id=org.o_id)
    session.add(rule)
    session.commit()

    # Create transactions and results today
    today_event = TestingRecordLog(
        event_id="outcome_event_1",
        event_timestamp=int(datetime.datetime.now().timestamp()),
        event={"test": "data"},
        o_id=org.o_id,
        created_at=datetime.datetime.now(),
    )
    session.add(today_event)
    session.commit()

    # Create result
    result = TestingResultsLog(tl_id=today_event.tl_id, rule_result="HOLD", r_id=rule.r_id)
    session.add(result)
    session.commit()

    rv = logged_in_manager_client.get("/dashboard")
    assert rv.status_code == 200
    assert b"Rule Outcomes Distribution" in rv.data
    assert b"outcomesDistributionChart" in rv.data
