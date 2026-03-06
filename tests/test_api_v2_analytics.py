"""
Tests for FastAPI v2 analytics endpoints.

These tests verify:
- Transaction volume endpoint
- Outcomes distribution endpoint
- Labels distribution endpoint
- Labels summary endpoint
- Rule quality endpoint
- Aggregation parameter validation
- Permission checks
"""

import datetime

import bcrypt
import pytest
from fastapi.testclient import TestClient

from ezrules.backend.api_v2.routes import analytics as analytics_routes
from ezrules.backend.api_v2.auth.jwt import create_access_token
from ezrules.backend.api_v2.main import app
from ezrules.backend.tasks import generate_rule_quality_report
from ezrules.core.permissions import PermissionManager
from ezrules.core.permissions_constants import PermissionAction
from ezrules.models.backend_core import (
    Label,
    Organisation,
    RuleQualityPair,
    RuleQualityReport,
    Role,
    TestingRecordLog,
    TestingResultsLog,
    User,
)
from ezrules.models.backend_core import Rule as RuleModel
from ezrules.settings import app_settings


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


@pytest.fixture(scope="function")
def sample_rule_quality_data(session):
    """Create deterministic labeled data for rule-quality metric tests."""
    org = session.query(Organisation).filter(Organisation.o_id == 1).first()
    if not org:
        org = Organisation(o_id=1, name="Test Org")
        session.add(org)
        session.commit()

    rule_a = RuleModel(
        rid="quality_rule_a",
        logic="return 'HOLD'",
        description="Rule A",
        o_id=org.o_id,
    )
    rule_b = RuleModel(
        rid="quality_rule_b",
        logic="return 'HOLD'",
        description="Rule B",
        o_id=org.o_id,
    )
    session.add_all([rule_a, rule_b])
    session.commit()

    fraud_label = Label(label="QUALITY_FRAUD")
    normal_label = Label(label="QUALITY_NORMAL")
    session.add_all([fraud_label, normal_label])
    session.commit()

    curated_pairs = [
        RuleQualityPair(
            outcome="HOLD",
            label=fraud_label.label,
            active=True,
            created_by="tests",
            o_id=org.o_id,
        ),
        RuleQualityPair(
            outcome="RELEASE",
            label=normal_label.label,
            active=True,
            created_by="tests",
            o_id=org.o_id,
        ),
    ]
    session.add_all(curated_pairs)
    session.commit()

    # Six labeled events. rule_b is perfect for HOLD->QUALITY_FRAUD and
    # RELEASE->QUALITY_NORMAL. rule_a is intentionally mixed.
    labels = [
        fraud_label.el_id,
        fraud_label.el_id,
        normal_label.el_id,
        normal_label.el_id,
        fraud_label.el_id,
        normal_label.el_id,
    ]
    rule_a_outcomes = ["HOLD", "RELEASE", "HOLD", "RELEASE", "HOLD", "RELEASE"]
    rule_b_outcomes = ["HOLD", "HOLD", "RELEASE", "RELEASE", "HOLD", "RELEASE"]

    now = datetime.datetime.now()
    for idx, label_id in enumerate(labels):
        event = TestingRecordLog(
            event_id=f"quality_event_{idx}",
            event={"idx": idx},
            event_timestamp=int((now - datetime.timedelta(minutes=idx)).timestamp()),
            o_id=org.o_id,
            el_id=label_id,
            created_at=now - datetime.timedelta(minutes=idx),
        )
        session.add(event)
        session.commit()

        session.add(
            TestingResultsLog(
                tl_id=event.tl_id,
                r_id=rule_a.r_id,
                rule_result=rule_a_outcomes[idx],
            )
        )
        session.add(
            TestingResultsLog(
                tl_id=event.tl_id,
                r_id=rule_b.r_id,
                rule_result=rule_b_outcomes[idx],
            )
        )

    session.commit()
    return {
        "rule_a": rule_a,
        "rule_b": rule_b,
        "fraud_label": fraud_label,
        "normal_label": normal_label,
        "curated_pairs": curated_pairs,
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
# RULE QUALITY TESTS
# =============================================================================


class TestRuleQuality:
    """Tests for GET /api/v2/analytics/rule-quality."""

    def test_rule_quality_with_data(self, analytics_test_client, sample_rule_quality_data):
        """Should return pair metrics and ranked best/worst rules."""
        token = analytics_test_client.test_data["token"]
        rule_a = sample_rule_quality_data["rule_a"]
        rule_b = sample_rule_quality_data["rule_b"]
        fraud_label = sample_rule_quality_data["fraud_label"]

        response = analytics_test_client.get(
            "/api/v2/analytics/rule-quality",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()

        assert data["total_labeled_events"] == 6
        assert data["min_support"] == 1
        assert data["lookback_days"] >= 1
        assert data["freeze_at"]
        assert len(data["pair_metrics"]) == 4
        assert len(data["best_rules"]) >= 1
        assert len(data["worst_rules"]) >= 1

        pair = next(
            metric
            for metric in data["pair_metrics"]
            if metric["r_id"] == rule_a.r_id and metric["outcome"] == "HOLD" and metric["label"] == fraud_label.label
        )
        assert pair["true_positive"] == 2
        assert pair["false_positive"] == 1
        assert pair["false_negative"] == 1
        assert pair["precision"] == pytest.approx(0.6667, rel=0, abs=1e-4)
        assert pair["recall"] == pytest.approx(0.6667, rel=0, abs=1e-4)
        assert pair["f1"] == pytest.approx(0.6667, rel=0, abs=1e-4)
        assert not any(
            metric["outcome"] == "HOLD" and metric["label"] == "QUALITY_NORMAL" for metric in data["pair_metrics"]
        )

        assert data["best_rules"][0]["r_id"] == rule_b.r_id
        assert data["worst_rules"][0]["r_id"] == rule_a.r_id

    def test_rule_quality_empty_when_no_active_curated_pairs(self, analytics_test_client, sample_rule_quality_data):
        token = analytics_test_client.test_data["token"]
        session = analytics_test_client.test_data["session"]

        for pair in sample_rule_quality_data["curated_pairs"]:
            pair.active = False
        session.commit()

        response = analytics_test_client.get(
            "/api/v2/analytics/rule-quality",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["total_labeled_events"] == 6
        assert payload["pair_metrics"] == []
        assert payload["best_rules"] == []
        assert payload["worst_rules"] == []

    def test_rule_quality_min_support_filter(self, analytics_test_client, sample_rule_quality_data):
        """Should filter out all pairs when support threshold is above data volume."""
        token = analytics_test_client.test_data["token"]

        response = analytics_test_client.get(
            "/api/v2/analytics/rule-quality?min_support=4",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["min_support"] == 4
        assert data["lookback_days"] >= 1
        assert data["freeze_at"]
        assert data["pair_metrics"] == []
        assert data["best_rules"] == []
        assert data["worst_rules"] == []

    def test_rule_quality_lookback_days_filter(self, analytics_test_client, sample_rule_quality_data):
        """Should exclude old labeled events outside the lookback window."""
        token = analytics_test_client.test_data["token"]
        session = analytics_test_client.test_data["session"]

        rule_a = sample_rule_quality_data["rule_a"]
        fraud_label = sample_rule_quality_data["fraud_label"]

        old_created_at = datetime.datetime.now() - datetime.timedelta(days=40)
        old_event = TestingRecordLog(
            event_id="quality_old_event",
            event={"idx": 999},
            event_timestamp=int(old_created_at.timestamp()),
            o_id=1,
            el_id=fraud_label.el_id,
            created_at=old_created_at,
        )
        session.add(old_event)
        session.commit()

        session.add(
            TestingResultsLog(
                tl_id=old_event.tl_id,
                r_id=rule_a.r_id,
                rule_result="HOLD",
            )
        )
        session.commit()

        recent_response = analytics_test_client.get(
            "/api/v2/analytics/rule-quality?lookback_days=1",
            headers={"Authorization": f"Bearer {token}"},
        )
        all_response = analytics_test_client.get(
            "/api/v2/analytics/rule-quality?lookback_days=90",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert recent_response.status_code == 200
        assert all_response.status_code == 200

        recent = recent_response.json()
        historical = all_response.json()
        assert recent["lookback_days"] == 1
        assert historical["lookback_days"] == 90
        assert recent["total_labeled_events"] == 6
        assert historical["total_labeled_events"] == 7

    def test_rule_quality_unauthorized(self, analytics_test_client):
        """Should return 401 without token."""
        response = analytics_test_client.get("/api/v2/analytics/rule-quality")
        assert response.status_code == 401


class TestRuleQualityReports:
    """Tests for async report lifecycle endpoints."""

    def test_rule_quality_report_request_and_get(self, analytics_test_client, sample_rule_quality_data, monkeypatch):
        """Should generate a report and return it via request/get endpoints."""
        token = analytics_test_client.test_data["token"]

        def fake_delay(report_id: int):
            generate_rule_quality_report(report_id)

            class FakeResult:
                id = "rule-quality-task-1"

            return FakeResult()

        monkeypatch.setattr(analytics_routes.generate_rule_quality_report, "delay", fake_delay)

        create_response = analytics_test_client.post(
            "/api/v2/analytics/rule-quality/reports",
            headers={"Authorization": f"Bearer {token}"},
            json={"min_support": 1, "lookback_days": 30},
        )
        assert create_response.status_code == 200
        created = create_response.json()
        assert created["status"] == "SUCCESS"
        assert created["cached"] is False
        assert created["result"] is not None
        assert created["result"]["freeze_at"]

        report_id = created["report_id"]
        get_response = analytics_test_client.get(
            f"/api/v2/analytics/rule-quality/reports/{report_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert get_response.status_code == 200
        fetched = get_response.json()
        assert fetched["report_id"] == report_id
        assert fetched["status"] == "SUCCESS"
        assert fetched["result"] is not None
        assert fetched["result"]["total_labeled_events"] == 6

    def test_rule_quality_report_reuses_cached_success(
        self,
        analytics_test_client,
        sample_rule_quality_data,
        monkeypatch,
    ):
        """Second identical request should reuse recent success report."""
        token = analytics_test_client.test_data["token"]
        session = analytics_test_client.test_data["session"]
        delay_calls = {"count": 0}

        def fake_delay(report_id: int):
            delay_calls["count"] += 1
            generate_rule_quality_report(report_id)

            class FakeResult:
                id = f"rule-quality-task-{delay_calls['count']}"

            return FakeResult()

        monkeypatch.setattr(analytics_routes.generate_rule_quality_report, "delay", fake_delay)

        first = analytics_test_client.post(
            "/api/v2/analytics/rule-quality/reports",
            headers={"Authorization": f"Bearer {token}"},
            json={"min_support": 1, "lookback_days": 30},
        )
        second = analytics_test_client.post(
            "/api/v2/analytics/rule-quality/reports",
            headers={"Authorization": f"Bearer {token}"},
            json={"min_support": 1, "lookback_days": 30},
        )

        assert first.status_code == 200
        assert second.status_code == 200
        first_data = first.json()
        second_data = second.json()
        assert first_data["report_id"] == second_data["report_id"]
        assert second_data["cached"] is True
        assert delay_calls["count"] == 1
        assert session.query(RuleQualityReport).count() == 1

    def test_rule_quality_report_force_refresh(
        self,
        analytics_test_client,
        sample_rule_quality_data,
        monkeypatch,
    ):
        """Force refresh should create a new report even with same params."""
        token = analytics_test_client.test_data["token"]
        delay_calls = {"count": 0}

        def fake_delay(report_id: int):
            delay_calls["count"] += 1
            generate_rule_quality_report(report_id)

            class FakeResult:
                id = f"rule-quality-task-refresh-{delay_calls['count']}"

            return FakeResult()

        monkeypatch.setattr(analytics_routes.generate_rule_quality_report, "delay", fake_delay)

        first = analytics_test_client.post(
            "/api/v2/analytics/rule-quality/reports",
            headers={"Authorization": f"Bearer {token}"},
            json={"min_support": 1, "lookback_days": 30},
        )
        refreshed = analytics_test_client.post(
            "/api/v2/analytics/rule-quality/reports",
            headers={"Authorization": f"Bearer {token}"},
            json={"min_support": 1, "lookback_days": 30, "force_refresh": True},
        )

        assert first.status_code == 200
        assert refreshed.status_code == 200
        assert first.json()["report_id"] != refreshed.json()["report_id"]
        assert refreshed.json()["cached"] is False
        assert delay_calls["count"] == 2

    def test_rule_quality_report_cache_invalidation_on_pair_change(
        self,
        analytics_test_client,
        sample_rule_quality_data,
        monkeypatch,
    ):
        token = analytics_test_client.test_data["token"]
        session = analytics_test_client.test_data["session"]
        delay_calls = {"count": 0}

        def fake_delay(report_id: int):
            delay_calls["count"] += 1
            generate_rule_quality_report(report_id)

            class FakeResult:
                id = f"rule-quality-task-pairs-{delay_calls['count']}"

            return FakeResult()

        monkeypatch.setattr(analytics_routes.generate_rule_quality_report, "delay", fake_delay)

        first = analytics_test_client.post(
            "/api/v2/analytics/rule-quality/reports",
            headers={"Authorization": f"Bearer {token}"},
            json={"min_support": 1, "lookback_days": 30},
        )
        assert first.status_code == 200

        extra_pair = RuleQualityPair(
            outcome="HOLD",
            label=sample_rule_quality_data["normal_label"].label,
            active=True,
            created_by="tests",
            o_id=app_settings.ORG_ID,
        )
        session.add(extra_pair)
        session.commit()

        second = analytics_test_client.post(
            "/api/v2/analytics/rule-quality/reports",
            headers={"Authorization": f"Bearer {token}"},
            json={"min_support": 1, "lookback_days": 30},
        )
        assert second.status_code == 200
        assert first.json()["report_id"] != second.json()["report_id"]
        assert second.json()["cached"] is False
        assert delay_calls["count"] == 2

    def test_rule_quality_report_pending(self, analytics_test_client, sample_rule_quality_data, monkeypatch):
        """If task is not executed yet, status should remain pending."""
        token = analytics_test_client.test_data["token"]
        monkeypatch.setattr(app_settings, "RULE_QUALITY_REPORT_SYNC_FALLBACK", False)

        def fake_delay(_report_id: int):
            class FakeResult:
                id = "rule-quality-task-pending"

            return FakeResult()

        monkeypatch.setattr(analytics_routes.generate_rule_quality_report, "delay", fake_delay)

        create_response = analytics_test_client.post(
            "/api/v2/analytics/rule-quality/reports",
            headers={"Authorization": f"Bearer {token}"},
            json={"min_support": 1, "lookback_days": 30},
        )
        assert create_response.status_code == 200
        created = create_response.json()
        assert created["status"] == "PENDING"
        assert created["result"] is None

        report_id = created["report_id"]
        get_response = analytics_test_client.get(
            f"/api/v2/analytics/rule-quality/reports/{report_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert get_response.status_code == 200
        fetched = get_response.json()
        assert fetched["status"] == "PENDING"
        assert fetched["result"] is None

    def test_rule_quality_report_sync_fallback(self, analytics_test_client, sample_rule_quality_data, monkeypatch):
        """GET status should compute report inline when fallback is enabled and task is still pending."""
        token = analytics_test_client.test_data["token"]
        monkeypatch.setattr(app_settings, "RULE_QUALITY_REPORT_SYNC_FALLBACK", True)

        def fake_delay(_report_id: int):
            class FakeResult:
                id = "rule-quality-task-pending-fallback"

            return FakeResult()

        monkeypatch.setattr(analytics_routes.generate_rule_quality_report, "delay", fake_delay)

        create_response = analytics_test_client.post(
            "/api/v2/analytics/rule-quality/reports",
            headers={"Authorization": f"Bearer {token}"},
            json={"min_support": 1, "lookback_days": 30},
        )
        assert create_response.status_code == 200
        created = create_response.json()
        assert created["status"] == "PENDING"

        report_id = created["report_id"]
        get_response = analytics_test_client.get(
            f"/api/v2/analytics/rule-quality/reports/{report_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert get_response.status_code == 200
        fetched = get_response.json()
        assert fetched["status"] == "SUCCESS"
        assert fetched["result"] is not None

    def test_rule_quality_report_not_found(self, analytics_test_client):
        """Unknown report ID should return 404."""
        token = analytics_test_client.test_data["token"]

        response = analytics_test_client.get(
            "/api/v2/analytics/rule-quality/reports/999999",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 404


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

    def test_rule_quality_without_label_permission(self, session):
        """User missing VIEW_LABELS should get 403 for rule-quality endpoint."""
        hashed_password = bcrypt.hashpw("norulequalitylabels".encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

        rules_only_role = Role(name="rules_only_rule_quality", description="Can only view rules")
        session.add(rules_only_role)
        session.commit()

        rules_only_user = User(
            email="rulesonly_rule_quality@example.com",
            password=hashed_password,
            active=True,
            fs_uniquifier="rulesonly_rule_quality@example.com",
        )
        rules_only_user.roles.append(rules_only_role)
        session.add(rules_only_user)
        session.commit()

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
                "/api/v2/analytics/rule-quality",
                headers={"Authorization": f"Bearer {token}"},
            )

            assert response.status_code == 403
