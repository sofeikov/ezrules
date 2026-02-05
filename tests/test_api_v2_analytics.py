"""
Tests for FastAPI v2 analytics endpoints.

These tests verify:
- Transaction volume endpoint
- Outcomes distribution endpoint
- Labels distribution endpoint
- Labels summary endpoint
- Aggregation parameter validation
- Permission checks
"""

import datetime

import bcrypt
import pytest
from fastapi.testclient import TestClient

from ezrules.backend.api_v2.auth.jwt import create_access_token
from ezrules.backend.api_v2.main import app
from ezrules.core.permissions import PermissionManager
from ezrules.core.permissions_constants import PermissionAction
from ezrules.models.backend_core import (
    Label,
    Organisation,
    Role,
    TestingRecordLog,
    TestingResultsLog,
    User,
)
from ezrules.models.backend_core import Rule as RuleModel


@pytest.fixture(scope="function")
def analytics_test_client(session):
    """
    Create a FastAPI test client with a user that has analytics permissions.
    """
    hashed_password = bcrypt.hashpw("analyticspass".encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    # Ensure organisation exists
    org = session.query(Organisation).filter(Organisation.o_id == 1).first()
    if not org:
        org = Organisation(o_id=1, name="Test Org")
        session.add(org)
        session.commit()

    # Create role with analytics permissions
    analytics_role = session.query(Role).filter(Role.name == "analytics_viewer").first()
    if not analytics_role:
        analytics_role = Role(name="analytics_viewer", description="Can view analytics")
        session.add(analytics_role)
        session.commit()

    # Create user with role
    analytics_user = session.query(User).filter(User.email == "analyticsuser@example.com").first()
    if not analytics_user:
        analytics_user = User(
            email="analyticsuser@example.com",
            password=hashed_password,
            active=True,
            fs_uniquifier="analyticsuser@example.com",
        )
        analytics_user.roles.append(analytics_role)
        session.add(analytics_user)
        session.commit()

    # Initialize permissions and grant them
    PermissionManager.db_session = session
    PermissionManager.init_default_actions()
    PermissionManager.grant_permission(analytics_role.id, PermissionAction.VIEW_RULES)
    PermissionManager.grant_permission(analytics_role.id, PermissionAction.VIEW_OUTCOMES)
    PermissionManager.grant_permission(analytics_role.id, PermissionAction.VIEW_LABELS)

    # Create a token for the user
    roles = [role.name for role in analytics_user.roles]
    token = create_access_token(
        user_id=int(analytics_user.id),
        email=str(analytics_user.email),
        roles=roles,
    )

    client_data = {
        "user": analytics_user,
        "role": analytics_role,
        "token": token,
        "session": session,
        "org": org,
    }

    with TestClient(app) as client:
        client.test_data = client_data  # type: ignore
        yield client


@pytest.fixture(scope="function")
def sample_analytics_data(session):
    """Create sample data for analytics testing."""
    org = session.query(Organisation).filter(Organisation.o_id == 1).first()
    if not org:
        org = Organisation(o_id=1, name="Test Org")
        session.add(org)
        session.commit()

    # Create a rule
    rule = RuleModel(
        rid="analytics_rule",
        logic="return 'HOLD'",
        description="Test rule for analytics",
        o_id=org.o_id,
    )
    session.add(rule)
    session.commit()

    # Create a label
    label = Label(label="ANALYTICS_TEST")
    session.add(label)
    session.commit()

    # Create test events (recent, within last hour)
    now = datetime.datetime.now()
    events = []
    for i in range(5):
        event = TestingRecordLog(
            event_id=f"analytics_event_{i}",
            event={"amount": 100 + i * 10},
            event_timestamp=int((now - datetime.timedelta(minutes=i * 5)).timestamp()),
            o_id=org.o_id,
            created_at=now - datetime.timedelta(minutes=i * 5),
        )
        # Assign label to some events
        if i < 3:
            event.el_id = label.el_id
        session.add(event)
        events.append(event)
    session.commit()

    # Create test results for the events
    for event in events:
        result = TestingResultsLog(
            tl_id=event.tl_id,
            r_id=rule.r_id,
            rule_result="HOLD" if event.event["amount"] > 110 else "RELEASE",
        )
        session.add(result)
    session.commit()

    return {
        "org": org,
        "rule": rule,
        "label": label,
        "events": events,
    }


# =============================================================================
# TRANSACTION VOLUME TESTS
# =============================================================================


class TestTransactionVolume:
    """Tests for GET /api/v2/analytics/transaction-volume."""

    def test_transaction_volume_empty(self, analytics_test_client):
        """Should return empty data when no transactions exist."""
        token = analytics_test_client.test_data["token"]

        response = analytics_test_client.get(
            "/api/v2/analytics/transaction-volume",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "labels" in data
        assert "data" in data
        assert "aggregation" in data
        assert data["aggregation"] == "1h"

    def test_transaction_volume_with_data(self, analytics_test_client, sample_analytics_data):
        """Should return transaction volume data."""
        token = analytics_test_client.test_data["token"]

        response = analytics_test_client.get(
            "/api/v2/analytics/transaction-volume",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data["labels"], list)
        assert isinstance(data["data"], list)

    def test_transaction_volume_aggregation_param(self, analytics_test_client):
        """Should respect aggregation parameter."""
        token = analytics_test_client.test_data["token"]

        for agg in ["1h", "6h", "12h", "24h", "30d"]:
            response = analytics_test_client.get(
                f"/api/v2/analytics/transaction-volume?aggregation={agg}",
                headers={"Authorization": f"Bearer {token}"},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["aggregation"] == agg

    def test_transaction_volume_invalid_aggregation(self, analytics_test_client):
        """Should return 400 for invalid aggregation."""
        token = analytics_test_client.test_data["token"]

        response = analytics_test_client.get(
            "/api/v2/analytics/transaction-volume?aggregation=invalid",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 400

    def test_transaction_volume_unauthorized(self, analytics_test_client):
        """Should return 401 without token."""
        response = analytics_test_client.get("/api/v2/analytics/transaction-volume")
        assert response.status_code == 401


# =============================================================================
# OUTCOMES DISTRIBUTION TESTS
# =============================================================================


class TestOutcomesDistribution:
    """Tests for GET /api/v2/analytics/outcomes-distribution."""

    def test_outcomes_distribution_empty(self, analytics_test_client):
        """Should return empty datasets when no outcomes exist."""
        token = analytics_test_client.test_data["token"]

        response = analytics_test_client.get(
            "/api/v2/analytics/outcomes-distribution",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "labels" in data
        assert "datasets" in data
        assert "aggregation" in data

    def test_outcomes_distribution_with_data(self, analytics_test_client, sample_analytics_data):
        """Should return outcomes distribution data."""
        token = analytics_test_client.test_data["token"]

        response = analytics_test_client.get(
            "/api/v2/analytics/outcomes-distribution",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data["labels"], list)
        assert isinstance(data["datasets"], list)
        # Each dataset should have Chart.js properties
        for dataset in data["datasets"]:
            assert "label" in dataset
            assert "data" in dataset
            assert "borderColor" in dataset
            assert "backgroundColor" in dataset

    def test_outcomes_distribution_invalid_aggregation(self, analytics_test_client):
        """Should return 400 for invalid aggregation."""
        token = analytics_test_client.test_data["token"]

        response = analytics_test_client.get(
            "/api/v2/analytics/outcomes-distribution?aggregation=invalid",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 400


# =============================================================================
# LABELS DISTRIBUTION TESTS
# =============================================================================


class TestLabelsDistribution:
    """Tests for GET /api/v2/analytics/labels-distribution."""

    def test_labels_distribution_empty(self, analytics_test_client):
        """Should return empty datasets when no labeled events exist."""
        token = analytics_test_client.test_data["token"]

        response = analytics_test_client.get(
            "/api/v2/analytics/labels-distribution",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "labels" in data
        assert "datasets" in data
        assert "aggregation" in data

    def test_labels_distribution_with_data(self, analytics_test_client, sample_analytics_data):
        """Should return labels distribution data."""
        token = analytics_test_client.test_data["token"]

        response = analytics_test_client.get(
            "/api/v2/analytics/labels-distribution",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data["labels"], list)
        assert isinstance(data["datasets"], list)

    def test_labels_distribution_invalid_aggregation(self, analytics_test_client):
        """Should return 400 for invalid aggregation."""
        token = analytics_test_client.test_data["token"]

        response = analytics_test_client.get(
            "/api/v2/analytics/labels-distribution?aggregation=invalid",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 400


# =============================================================================
# LABELED TRANSACTION VOLUME TESTS
# =============================================================================


class TestLabeledTransactionVolume:
    """Tests for GET /api/v2/analytics/labeled-transaction-volume."""

    def test_labeled_transaction_volume_empty(self, analytics_test_client):
        """Should return empty data when no labeled transactions exist."""
        token = analytics_test_client.test_data["token"]

        response = analytics_test_client.get(
            "/api/v2/analytics/labeled-transaction-volume",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "labels" in data
        assert "data" in data
        assert "aggregation" in data

    def test_labeled_transaction_volume_with_data(self, analytics_test_client, sample_analytics_data):
        """Should return labeled transaction volume data."""
        token = analytics_test_client.test_data["token"]

        response = analytics_test_client.get(
            "/api/v2/analytics/labeled-transaction-volume",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data["labels"], list)
        assert isinstance(data["data"], list)

    def test_labeled_transaction_volume_invalid_aggregation(self, analytics_test_client):
        """Should return 400 for invalid aggregation."""
        token = analytics_test_client.test_data["token"]

        response = analytics_test_client.get(
            "/api/v2/analytics/labeled-transaction-volume?aggregation=invalid",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 400


# =============================================================================
# LABELS SUMMARY TESTS
# =============================================================================


class TestLabelsSummary:
    """Tests for GET /api/v2/analytics/labels-summary."""

    def test_labels_summary_empty(self, analytics_test_client):
        """Should return zero counts when no labeled events exist."""
        token = analytics_test_client.test_data["token"]

        response = analytics_test_client.get(
            "/api/v2/analytics/labels-summary",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "total_labeled" in data
        assert "pie_chart" in data
        assert data["total_labeled"] == 0

    def test_labels_summary_with_data(self, analytics_test_client, sample_analytics_data):
        """Should return labels summary with pie chart data."""
        token = analytics_test_client.test_data["token"]

        response = analytics_test_client.get(
            "/api/v2/analytics/labels-summary",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total_labeled"] >= 0
        assert "pie_chart" in data
        assert "labels" in data["pie_chart"]
        assert "data" in data["pie_chart"]
        assert "backgroundColor" in data["pie_chart"]

    def test_labels_summary_unauthorized(self, analytics_test_client):
        """Should return 401 without token."""
        response = analytics_test_client.get("/api/v2/analytics/labels-summary")
        assert response.status_code == 401


# =============================================================================
# PERMISSION TESTS
# =============================================================================


class TestAnalyticsPermissions:
    """Tests for permission checks on analytics endpoints."""

    def test_transaction_volume_without_permission(self, session):
        """User without VIEW_RULES permission should get 403."""
        hashed_password = bcrypt.hashpw("noviewpass".encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

        # Create user without permissions
        no_perm_user = User(
            email="noperm_analytics@example.com",
            password=hashed_password,
            active=True,
            fs_uniquifier="noperm_analytics@example.com",
        )
        session.add(no_perm_user)
        session.commit()

        # Initialize permissions (but don't grant any to this user)
        PermissionManager.db_session = session
        PermissionManager.init_default_actions()

        token = create_access_token(
            user_id=int(no_perm_user.id),
            email=str(no_perm_user.email),
            roles=[],
        )

        with TestClient(app) as client:
            response = client.get(
                "/api/v2/analytics/transaction-volume",
                headers={"Authorization": f"Bearer {token}"},
            )

            assert response.status_code == 403

    def test_labels_summary_without_permission(self, session):
        """User without VIEW_LABELS permission should get 403."""
        hashed_password = bcrypt.hashpw("nolabelspass".encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

        # Create role with only VIEW_RULES permission
        rules_only_role = Role(name="rules_only_analytics", description="Can only view rules")
        session.add(rules_only_role)
        session.commit()

        # Create user with rules-only role
        rules_only_user = User(
            email="rulesonly_analytics@example.com",
            password=hashed_password,
            active=True,
            fs_uniquifier="rulesonly_analytics@example.com",
        )
        rules_only_user.roles.append(rules_only_role)
        session.add(rules_only_user)
        session.commit()

        # Initialize permissions and grant only VIEW_RULES
        PermissionManager.db_session = session
        PermissionManager.init_default_actions()
        PermissionManager.grant_permission(rules_only_role.id, PermissionAction.VIEW_RULES)

        token = create_access_token(
            user_id=int(rules_only_user.id),
            email=str(rules_only_user.email),
            roles=[rules_only_role.name],
        )

        with TestClient(app) as client:
            response = client.get(
                "/api/v2/analytics/labels-summary",
                headers={"Authorization": f"Bearer {token}"},
            )

            assert response.status_code == 403
