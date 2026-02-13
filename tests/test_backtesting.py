import bcrypt
import pytest
from fastapi.testclient import TestClient

from ezrules.backend.api_v2.auth.jwt import create_access_token
from ezrules.backend.api_v2.main import app
from ezrules.backend.tasks import app as celery_app
from ezrules.backend.tasks import backtest_rule_change
from ezrules.core.permissions import PermissionManager
from ezrules.core.permissions_constants import PermissionAction
from ezrules.models.backend_core import Organisation, Role, RuleBackTestingResult, TestingRecordLog, User
from ezrules.models.backend_core import Rule as RuleModel


@pytest.fixture(scope="function")
def backtesting_test_client(session):
    """Create a FastAPI test client with a user that has rule permissions."""
    # Enable eager mode so .delay() runs synchronously
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True

    hashed_password = bcrypt.hashpw("btpass".encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    org = session.query(Organisation).filter(Organisation.o_id == 1).first()
    if not org:
        org = Organisation(o_id=1, name="Test Org")
        session.add(org)
        session.commit()

    role = session.query(Role).filter(Role.name == "bt_manager").first()
    if not role:
        role = Role(name="bt_manager", description="Can manage backtests")
        session.add(role)
        session.commit()

    user = session.query(User).filter(User.email == "btuser@example.com").first()
    if not user:
        user = User(
            email="btuser@example.com",
            password=hashed_password,
            active=True,
            fs_uniquifier="btuser@example.com",
        )
        user.roles.append(role)
        session.add(user)
        session.commit()

    PermissionManager.db_session = session
    PermissionManager.init_default_actions()
    PermissionManager.grant_permission(role.id, PermissionAction.VIEW_RULES)
    PermissionManager.grant_permission(role.id, PermissionAction.MODIFY_RULE)

    roles = [r.name for r in user.roles]
    token = create_access_token(
        user_id=int(user.id),
        email=str(user.email),
        roles=roles,
    )

    client_data = {
        "user": user,
        "role": role,
        "token": token,
        "session": session,
        "org": org,
    }

    with TestClient(app) as client:
        client.test_data = client_data  # type: ignore[attr-defined]
        yield client

    celery_app.conf.task_always_eager = False
    celery_app.conf.task_eager_propagates = False


@pytest.fixture(scope="function")
def sample_rule_for_bt(session):
    """Create a sample rule for backtesting."""
    org = session.query(Organisation).filter(Organisation.o_id == 1).first()
    if not org:
        org = Organisation(o_id=1, name="Test Org")
        session.add(org)
        session.commit()

    rule = RuleModel(
        rid="bt_rule_001",
        logic='if $amount > 100:\n\treturn "HOLD"',
        description="Backtest rule",
        o_id=org.o_id,
    )
    session.add(rule)
    session.commit()
    return rule


class TestBacktestTaskDirect:
    """Tests for the backtest_rule_change Celery task called directly."""

    def test_backtest_with_records(self, session, sample_rule_for_bt):
        """Insert TestingRecordLog rows, run the task, verify outcome counts."""
        celery_app.conf.task_always_eager = True
        celery_app.conf.task_eager_propagates = True

        org = session.query(Organisation).filter(Organisation.o_id == 1).first()

        # Insert test records
        for i in range(10):
            record = TestingRecordLog(
                event={"amount": 50 + i * 20},  # amounts: 50, 70, 90, 110, 130, 150, 170, 190, 210, 230
                event_timestamp=1000000 + i,
                event_id=f"evt_{i}",
                o_id=org.o_id,
            )
            session.add(record)
        session.commit()

        # Run the task directly
        result = backtest_rule_change(sample_rule_for_bt.r_id, 'if $amount > 150:\n\treturn "BLOCK"')

        assert "error" not in result
        assert "stored_result" in result
        assert "proposed_result" in result
        assert "total_records" in result
        assert result["total_records"] == 10

        # stored rule: amount > 100 => HOLD for amounts 110,130,150,170,190,210,230 = 7
        assert result["stored_result"].get("HOLD") == 7

        # proposed rule: amount > 150 => BLOCK for amounts 170,190,210,230 = 4
        assert result["proposed_result"].get("BLOCK") == 4

        celery_app.conf.task_always_eager = False
        celery_app.conf.task_eager_propagates = False

    def test_backtest_nonexistent_rule(self, session):
        """Task should return error for non-existent rule."""
        celery_app.conf.task_always_eager = True
        celery_app.conf.task_eager_propagates = True

        result = backtest_rule_change(99999, "return True")

        assert "error" in result
        assert "not found" in result["error"]

        celery_app.conf.task_always_eager = False
        celery_app.conf.task_eager_propagates = False


class TestBacktestPostEndpoint:
    """Tests for POST /api/v2/backtesting."""

    def test_trigger_backtest_bad_logic(self, backtesting_test_client, sample_rule_for_bt):
        """Should return 400 for invalid proposed logic."""
        token = backtesting_test_client.test_data["token"]

        response = backtesting_test_client.post(
            "/api/v2/backtesting",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "r_id": sample_rule_for_bt.r_id,
                "new_rule_logic": "invalid {{{ syntax",
            },
        )

        assert response.status_code == 400

    def test_trigger_backtest_nonexistent_rule(self, backtesting_test_client):
        """Should return 404 for non-existent rule."""
        token = backtesting_test_client.test_data["token"]

        response = backtesting_test_client.post(
            "/api/v2/backtesting",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "r_id": 99999,
                "new_rule_logic": "return True",
            },
        )

        assert response.status_code == 404

    def test_trigger_backtest_happy_path(self, backtesting_test_client, sample_rule_for_bt):
        """Should create RuleBackTestingResult and return task ID."""
        token = backtesting_test_client.test_data["token"]
        session = backtesting_test_client.test_data["session"]

        response = backtesting_test_client.post(
            "/api/v2/backtesting",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "r_id": sample_rule_for_bt.r_id,
                "new_rule_logic": "return True",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["task_id"] != ""
        assert data["message"] == "Backtest started"

        # Verify RuleBackTestingResult was created in DB
        bt_result = (
            session.query(RuleBackTestingResult).filter(RuleBackTestingResult.task_id == data["task_id"]).first()
        )
        assert bt_result is not None
        assert bt_result.r_id == sample_rule_for_bt.r_id


class TestBacktestGetEndpoint:
    """Tests for GET /api/v2/backtesting/{rule_id}."""

    def test_get_results_empty(self, backtesting_test_client):
        """Should return empty results for rule with no backtests."""
        token = backtesting_test_client.test_data["token"]

        response = backtesting_test_client.get(
            "/api/v2/backtesting/99999",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["results"] == []

    def test_get_results_returns_most_recent(self, backtesting_test_client, sample_rule_for_bt):
        """Should return 3 most recent results."""
        token = backtesting_test_client.test_data["token"]
        session = backtesting_test_client.test_data["session"]

        # Insert 5 backtesting results
        for i in range(5):
            bt = RuleBackTestingResult(
                r_id=sample_rule_for_bt.r_id,
                task_id=f"task-{i}",
            )
            session.add(bt)
        session.commit()

        response = backtesting_test_client.get(
            f"/api/v2/backtesting/{sample_rule_for_bt.r_id}",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["results"]) == 3


class TestBacktestChunkedEvaluation:
    """Test that Counter-based accumulation works correctly with chunked reads."""

    def test_chunked_evaluation_accumulation(self, session, sample_rule_for_bt):
        """Insert enough records to verify Counter accumulates correctly."""
        celery_app.conf.task_always_eager = True
        celery_app.conf.task_eager_propagates = True

        org = session.query(Organisation).filter(Organisation.o_id == 1).first()

        # Insert 50 records: 25 with amount > 100, 25 with amount <= 100
        for i in range(50):
            amount = 200 if i < 25 else 50
            record = TestingRecordLog(
                event={"amount": amount},
                event_timestamp=2000000 + i,
                event_id=f"chunk_evt_{i}",
                o_id=org.o_id,
            )
            session.add(record)
        session.commit()

        result = backtest_rule_change(sample_rule_for_bt.r_id, 'if $amount > 50:\n\treturn "FLAG"')

        assert "error" not in result
        assert result["total_records"] == 50
        # stored rule: amount > 100 => HOLD for 25 records
        assert result["stored_result"].get("HOLD") == 25
        # proposed rule: amount > 50 => FLAG for 25 records (amount=200)
        assert result["proposed_result"].get("FLAG") == 25

        celery_app.conf.task_always_eager = False
        celery_app.conf.task_eager_propagates = False
