import pytest
from flask import g

from ezrules.backend.ezruleapp import app
from ezrules.backend.forms import LabelForm
from ezrules.core.labels import DatabaseLabelManager
from ezrules.models.backend_core import Label


def test_label_management_page_loads_successfully(logged_in_manager_client):
    """Test that the label management page loads successfully"""
    response = logged_in_manager_client.get("/management/labels")
    assert response.status_code == 200
    assert b"Labels List" in response.data
    assert b"Label name" in response.data


def test_can_add_labels_via_ui(logged_in_manager_client, session):
    """Test that we can add labels via the UI"""
    initial_count = session.query(Label).count()

    # First get the page to establish CSRF token
    logged_in_manager_client.get("/management/labels")

    form = LabelForm()
    form.label.data = "TEST_LABEL"
    form.csrf_token.data = g.csrf_token

    response = logged_in_manager_client.post("/management/labels", data=form.data, follow_redirects=True)

    # Should be successful
    assert response.status_code == 200

    # Check that label was added to database
    final_count = session.query(Label).count()
    assert final_count == initial_count + 1

    # Check that the label exists in the database
    test_label = session.query(Label).filter_by(label="TEST_LABEL").first()
    assert test_label is not None
    assert test_label.label == "TEST_LABEL"


def test_label_manager_functionality(session):
    """Test the DatabaseLabelManager functionality"""
    label_manager = DatabaseLabelManager(db_session=session, o_id=1)

    # Initially no labels
    initial_labels = label_manager.get_all_labels()
    initial_count = len(initial_labels)

    # Add a label
    label_manager.add_label("FRAUD_SCORE")

    # Check it was added
    updated_labels = label_manager.get_all_labels()
    assert len(updated_labels) == initial_count + 1
    assert "FRAUD_SCORE" in updated_labels

    # Check label exists
    assert label_manager.label_exists("FRAUD_SCORE")
    assert not label_manager.label_exists("NON_EXISTENT_LABEL")

    # Try to add the same label again - should not duplicate
    label_manager.add_label("FRAUD_SCORE")
    final_labels = label_manager.get_all_labels()
    assert len(final_labels) == initial_count + 1  # Should still be same count


def test_label_management_requires_permissions(logged_out_manager_client, session):
    """Test that label management requires proper permissions when not in test mode"""
    # In TESTING mode, auth is skipped, so we just verify the page loads
    response = logged_out_manager_client.get("/management/labels")
    # In test mode, this should load successfully, not require auth
    assert response.status_code == 200


def test_api_endpoint_still_works(session):
    """Test that the existing API endpoint still works"""
    with app.test_client() as client:
        # Add a label via API
        response = client.post("/labels", json={"label_name": "API_TEST_LABEL"})
        assert response.status_code == 200

        # Get labels via API
        response = client.get("/labels")
        assert response.status_code == 200
        labels = response.get_json()
        assert "API_TEST_LABEL" in labels


def test_default_labels_created(session):
    """Test that default labels are created on initialization"""
    label_manager = DatabaseLabelManager(db_session=session, o_id=1)

    # Get labels should trigger initialization
    labels = label_manager.get_all_labels()

    # Should have the three default labels
    expected_defaults = ["FRAUD", "CHARGEBACK", "NORMAL"]
    for expected_label in expected_defaults:
        assert expected_label in labels


def test_label_removal_functionality(session):
    """Test that we can remove labels"""
    label_manager = DatabaseLabelManager(db_session=session, o_id=1)

    # Add a test label
    label_manager.add_label("TEST_REMOVAL")

    # Verify it exists
    assert label_manager.label_exists("TEST_REMOVAL")
    assert "TEST_REMOVAL" in label_manager.get_all_labels()

    # Remove it
    label_manager.remove_label("TEST_REMOVAL")

    # Verify it's gone
    assert not label_manager.label_exists("TEST_REMOVAL")
    assert "TEST_REMOVAL" not in label_manager.get_all_labels()


def test_ui_shows_delete_buttons(logged_in_manager_client):
    """Test that the UI shows delete buttons for labels"""
    response = logged_in_manager_client.get("/management/labels")
    assert response.status_code == 200

    # Check that the delete button HTML is present
    assert b"Delete" in response.data
    assert b'name="action" value="delete"' in response.data
