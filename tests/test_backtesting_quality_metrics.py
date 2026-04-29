import bcrypt
import pytest
from fastapi.testclient import TestClient

from ezrules.backend.api_v2.auth.jwt import create_access_token
from ezrules.backend.api_v2.main import app
from ezrules.backend.api_v2.routes import backtesting as backtesting_routes
from ezrules.backend.tasks import backtest_rule_change
from ezrules.core.permissions import PermissionManager
from ezrules.core.permissions_constants import PermissionAction
from ezrules.models.backend_core import Label, Organisation, Role, RuleBackTestingResult, User
from ezrules.models.backend_core import Rule as RuleModel
from tests.canonical_helpers import add_served_decision


@pytest.fixture(scope="function")
def backtesting_quality_client(session):
    hashed_password = bcrypt.hashpw(b"btpass", bcrypt.gensalt()).decode("utf-8")

    org = session.query(Organisation).filter(Organisation.o_id == 1).first()
    if org is None:
        org = Organisation(o_id=1, name="Backtesting Quality Org")
        session.add(org)
        session.commit()

    role = session.query(Role).filter(Role.name == "bt_quality_manager", Role.o_id == int(org.o_id)).first()
    if role is None:
        role = Role(
            name="bt_quality_manager",
            description="Can inspect backtesting quality metrics",
            o_id=int(org.o_id),
        )
        session.add(role)
        session.commit()

    user = session.query(User).filter(User.email == "bt-quality@example.com").first()
    if user is None:
        user = User(
            email="bt-quality@example.com",
            password=hashed_password,
            active=True,
            fs_uniquifier="bt-quality@example.com",
            o_id=1,
        )
        user.roles.append(role)
        session.add(user)
        session.commit()

    PermissionManager.db_session = session
    PermissionManager.init_default_actions()
    PermissionManager.grant_permission(role.id, PermissionAction.VIEW_RULES)
    PermissionManager.grant_permission(role.id, PermissionAction.MODIFY_RULE)

    token = create_access_token(
        user_id=int(user.id),
        email=str(user.email),
        roles=[item.name for item in user.roles],
        org_id=int(user.o_id),
    )

    with TestClient(app) as client:
        client.test_data = {"token": token, "session": session}  # type: ignore[attr-defined]
        yield client


@pytest.fixture(scope="function")
def labeled_backtest_fixture(session):
    org = session.query(Organisation).filter(Organisation.o_id == 1).first()
    if org is None:
        org = Organisation(o_id=1, name="Backtesting Quality Org")
        session.add(org)
        session.commit()

    fraud_label = Label(label="FRAUD", o_id=int(org.o_id))
    normal_label = Label(label="NORMAL", o_id=int(org.o_id))
    session.add_all([fraud_label, normal_label])
    session.commit()

    rule = RuleModel(
        rid="bt_quality_rule",
        logic="if $amount > 100:\n\treturn !HOLD",
        description="Backtesting quality coverage rule",
        o_id=org.o_id,
    )
    session.add(rule)
    session.commit()

    records = [
        {"event_id": "quality_evt_1", "amount": 200, "label": fraud_label},
        {"event_id": "quality_evt_2", "amount": 180, "label": fraud_label},
        {"event_id": "quality_evt_3", "amount": 120, "label": normal_label},
        {"event_id": "quality_evt_4", "amount": 80, "label": normal_label},
        {"event_id": "quality_evt_5", "amount": 220, "label": None},
        {"event_id": "quality_evt_6", "amount": 60, "label": None},
    ]

    for index, record in enumerate(records):
        add_served_decision(
            session,
            org_id=int(org.o_id),
            event_id=record["event_id"],
            event_timestamp=1_900_000 + index,
            event_data={"amount": record["amount"]},
            label=record["label"],
        )
    session.commit()

    return {"org": org, "rule": rule}


def test_backtest_task_returns_label_counts_and_quality_metrics(session, labeled_backtest_fixture):
    result = backtest_rule_change(
        labeled_backtest_fixture["rule"].r_id,
        "if $amount > 150:\n\treturn !BLOCK",
        int(labeled_backtest_fixture["org"].o_id),
    )

    assert result["total_records"] == 6
    assert result["labeled_records"] == 4
    assert result["label_counts"] == {"FRAUD": 2, "NORMAL": 2}

    assert result["stored_result"] == {"HOLD": 4}
    assert result["proposed_result"] == {"BLOCK": 3}
    assert result["stored_result_rate"]["HOLD"] == pytest.approx(66.6667, abs=1e-4)
    assert result["proposed_result_rate"]["BLOCK"] == pytest.approx(50.0, abs=1e-4)

    stored_metrics = {(metric["outcome"], metric["label"]): metric for metric in result["stored_quality_metrics"]}
    proposed_metrics = {(metric["outcome"], metric["label"]): metric for metric in result["proposed_quality_metrics"]}

    assert stored_metrics[("HOLD", "FRAUD")]["predicted_positives"] == 3
    assert stored_metrics[("HOLD", "FRAUD")]["actual_positives"] == 2
    assert stored_metrics[("HOLD", "FRAUD")]["precision"] == pytest.approx(0.6667, abs=1e-4)
    assert stored_metrics[("HOLD", "FRAUD")]["recall"] == pytest.approx(1.0, abs=1e-4)
    assert stored_metrics[("HOLD", "FRAUD")]["f1"] == pytest.approx(0.8, abs=1e-4)

    assert stored_metrics[("BLOCK", "FRAUD")]["predicted_positives"] == 0
    assert stored_metrics[("BLOCK", "FRAUD")]["precision"] is None
    assert stored_metrics[("BLOCK", "FRAUD")]["recall"] == pytest.approx(0.0, abs=1e-4)

    assert proposed_metrics[("BLOCK", "FRAUD")]["predicted_positives"] == 2
    assert proposed_metrics[("BLOCK", "FRAUD")]["precision"] == pytest.approx(1.0, abs=1e-4)
    assert proposed_metrics[("BLOCK", "FRAUD")]["recall"] == pytest.approx(1.0, abs=1e-4)
    assert proposed_metrics[("BLOCK", "FRAUD")]["f1"] == pytest.approx(1.0, abs=1e-4)
    assert proposed_metrics[("BLOCK", "NORMAL")]["precision"] == pytest.approx(0.0, abs=1e-4)
    assert proposed_metrics[("BLOCK", "NORMAL")]["recall"] == pytest.approx(0.0, abs=1e-4)
    assert proposed_metrics[("BLOCK", "NORMAL")]["f1"] == pytest.approx(0.0, abs=1e-4)

    assert result["stored_quality_summary"]["pair_count"] == 2
    assert result["stored_quality_summary"]["average_precision"] == pytest.approx(0.5, abs=1e-4)
    assert result["stored_quality_summary"]["average_recall"] == pytest.approx(0.75, abs=1e-4)
    assert result["stored_quality_summary"]["average_f1"] == pytest.approx(0.6, abs=1e-4)
    assert result["stored_quality_summary"]["best_pair"] == "HOLD -> FRAUD"
    assert result["stored_quality_summary"]["worst_pair"] == "HOLD -> NORMAL"

    assert result["proposed_quality_summary"]["pair_count"] == 2
    assert result["proposed_quality_summary"]["average_precision"] == pytest.approx(0.5, abs=1e-4)
    assert result["proposed_quality_summary"]["average_recall"] == pytest.approx(0.5, abs=1e-4)
    assert result["proposed_quality_summary"]["average_f1"] == pytest.approx(0.5, abs=1e-4)
    assert result["proposed_quality_summary"]["best_pair"] == "BLOCK -> FRAUD"
    assert result["proposed_quality_summary"]["worst_pair"] == "BLOCK -> NORMAL"


def test_get_task_result_serializes_quality_metrics(backtesting_quality_client, monkeypatch):
    class FakeAsyncResult:
        state = "SUCCESS"
        result = {
            "stored_result": {"HOLD": 12},
            "proposed_result": {"BLOCK": 8},
            "stored_result_rate": {"HOLD": 60.0},
            "proposed_result_rate": {"BLOCK": 40.0},
            "total_records": 20,
            "labeled_records": 5,
            "label_counts": {"FRAUD": 3, "NORMAL": 2},
            "stored_quality_summary": {
                "pair_count": 1,
                "average_precision": 0.75,
                "average_recall": 1.0,
                "average_f1": 0.8571,
                "best_pair": "HOLD -> FRAUD",
                "worst_pair": "HOLD -> FRAUD",
            },
            "proposed_quality_summary": {
                "pair_count": 1,
                "average_precision": 1.0,
                "average_recall": 0.6667,
                "average_f1": 0.8,
                "best_pair": "BLOCK -> FRAUD",
                "worst_pair": "BLOCK -> FRAUD",
            },
            "stored_quality_metrics": [
                {
                    "outcome": "HOLD",
                    "label": "FRAUD",
                    "true_positive": 3,
                    "false_positive": 1,
                    "false_negative": 0,
                    "predicted_positives": 4,
                    "actual_positives": 3,
                    "precision": 0.75,
                    "recall": 1.0,
                    "f1": 0.8571,
                }
            ],
            "proposed_quality_metrics": [
                {
                    "outcome": "BLOCK",
                    "label": "FRAUD",
                    "true_positive": 2,
                    "false_positive": 0,
                    "false_negative": 1,
                    "predicted_positives": 2,
                    "actual_positives": 3,
                    "precision": 1.0,
                    "recall": 0.6667,
                    "f1": 0.8,
                }
            ],
        }

        def __init__(self, task_id, app):  # noqa: ARG002
            pass

    monkeypatch.setattr(backtesting_routes, "AsyncResult", FakeAsyncResult)

    session = backtesting_quality_client.test_data["session"]
    org = session.query(Organisation).filter(Organisation.o_id == 1).one()
    rule = RuleModel(
        rid="bt_quality_task_rule",
        logic="return !HOLD",
        description="Backtesting task status rule",
        o_id=int(org.o_id),
    )
    session.add(rule)
    session.commit()
    session.add(
        RuleBackTestingResult(
            r_id=int(rule.r_id),
            task_id="fake-task-id",
        )
    )
    session.commit()

    response = backtesting_quality_client.get(
        "/api/v2/backtesting/task/fake-task-id",
        headers={"Authorization": f"Bearer {backtesting_quality_client.test_data['token']}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "SUCCESS"
    assert data["labeled_records"] == 5
    assert data["label_counts"] == {"FRAUD": 3, "NORMAL": 2}
    assert data["stored_quality_summary"]["average_f1"] == pytest.approx(0.8571, abs=1e-4)
    assert data["proposed_quality_metrics"][0]["outcome"] == "BLOCK"
    assert data["proposed_quality_metrics"][0]["label"] == "FRAUD"
