import hashlib
import json
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import bcrypt
import pytest
import yaml
from fastapi.testclient import TestClient

from ezrules.backend import shadow_evaluation_queue
from ezrules.backend.api_v2.auth.jwt import create_access_token
from ezrules.backend.api_v2.main import app
from ezrules.backend.api_v2.routes import evaluator as evaluator_router
from ezrules.backend.features import persist_graph_links_for_event
from ezrules.backend.tasks import app as celery_app
from ezrules.core.permissions import PermissionManager
from ezrules.core.permissions_constants import PermissionAction
from ezrules.core.rule_updater import RDBRuleEngineConfigProducer, RDBRuleManager
from ezrules.models.backend_core import (
    AllowedOutcome,
    EventVersion,
    EventVersionLabel,
    FeatureDefinition,
    GraphEntityField,
    GraphEventEntityLink,
    Label,
    Organisation,
    Role,
    RuleBackTestingResult,
    RuleDeploymentResultsLog,
    RuleHistory,
    RuleQualityPair,
    User,
)
from ezrules.models.backend_core import Rule as RuleModel

SCENARIO_DIR = Path(__file__).parent
SCENARIO_FILES = [
    "canonical_rule_lifecycle_scenarios.yaml",
    "canonical_shadow_rollout_scenarios.yaml",
    "canonical_labels_audit_scenarios.yaml",
    "canonical_graph_feature_scenarios.yaml",
    "canonical_backtesting_scenarios.yaml",
]

MANAGER_PERMISSIONS = [
    PermissionAction.VIEW_RULES,
    PermissionAction.CREATE_RULE,
    PermissionAction.MODIFY_RULE,
    PermissionAction.PROMOTE_RULES,
    PermissionAction.PAUSE_RULES,
    PermissionAction.DELETE_RULE,
    PermissionAction.GENERATE_RULE_QUALITY_REPORTS,
    PermissionAction.SUBMIT_TEST_EVENTS,
    PermissionAction.VIEW_LISTS,
    PermissionAction.CREATE_LIST,
    PermissionAction.MODIFY_LIST,
    PermissionAction.DELETE_LIST,
    PermissionAction.VIEW_LABELS,
    PermissionAction.CREATE_LABEL,
    PermissionAction.DELETE_LABEL,
    PermissionAction.ACCESS_AUDIT_TRAIL,
]


class FakeRedisLock:
    def __init__(self, state: dict[str, bool], name: str) -> None:
        self._state = state
        self._name = name
        self._held = False

    def acquire(self, blocking: bool = False) -> bool:
        del blocking
        if self._state.get(self._name, False):
            return False
        self._state[self._name] = True
        self._held = True
        return True

    def release(self) -> None:
        if self._held:
            self._state[self._name] = False
            self._held = False


class FakeRedis:
    def __init__(self) -> None:
        self._lists: dict[str, list[str]] = {}
        self._lock_state: dict[str, bool] = {}

    def lpush(self, name: str, *values: str) -> int:
        queue = self._lists.setdefault(name, [])
        for value in values:
            queue.insert(0, value)
        return len(queue)

    def rpush(self, name: str, *values: str) -> int:
        queue = self._lists.setdefault(name, [])
        queue.extend(values)
        return len(queue)

    def rpop(self, name: str, count: int | None = None) -> str | list[str] | None:
        queue = self._lists.setdefault(name, [])
        if not queue:
            return None
        if count is None:
            return queue.pop()

        popped: list[str] = []
        for _ in range(min(count, len(queue))):
            popped.append(queue.pop())
        return popped

    def lock(self, name: str, timeout: int | None = None, blocking: bool = False) -> FakeRedisLock:
        del timeout, blocking
        return FakeRedisLock(self._lock_state, name)


def _load_suite(filename: str) -> dict[str, Any]:
    with (SCENARIO_DIR / filename).open() as file:
        return yaml.safe_load(file)


SUITES = [_load_suite(filename) for filename in SCENARIO_FILES]
SCENARIOS = [(suite, scenario) for suite in SUITES for scenario in suite["scenarios"]]


def _scenario_id(param: tuple[dict[str, Any], dict[str, Any]]) -> str:
    suite, scenario = param
    return f"{suite['name']}::{scenario['id']}"


@pytest.fixture(autouse=True)
def reset_runtime_state() -> Iterator[None]:
    evaluator_router._lre = None
    evaluator_router._shadow_lre = None
    evaluator_router._allowlist_lre = None
    previous_always_eager = celery_app.conf.task_always_eager
    previous_eager_propagates = celery_app.conf.task_eager_propagates
    yield
    evaluator_router._lre = None
    evaluator_router._shadow_lre = None
    evaluator_router._allowlist_lre = None
    celery_app.conf.task_always_eager = previous_always_eager
    celery_app.conf.task_eager_propagates = previous_eager_propagates


def _seed_outcomes(session, suite: dict[str, Any], *, org_id: int) -> None:
    session.query(AllowedOutcome).filter(AllowedOutcome.o_id == org_id).delete(synchronize_session=False)
    for outcome in suite["outcomes"]:
        session.add(
            AllowedOutcome(
                outcome_name=str(outcome["name"]),
                severity_rank=int(outcome["severity_rank"]),
                o_id=org_id,
            )
        )
    session.commit()


def _manager_token(session, *, email: str) -> str:
    org = session.query(Organisation).one()
    role = Role(name=f"canonical_role_{email}", description="Canonical scenario manager", o_id=int(org.o_id))
    user = User(
        email=email,
        password=bcrypt.hashpw(b"canonicalpass", bcrypt.gensalt()).decode("utf-8"),
        active=True,
        fs_uniquifier=email,
        o_id=int(org.o_id),
    )
    user.roles.append(role)
    session.add_all([role, user])
    session.commit()

    PermissionManager.db_session = session
    PermissionManager.init_default_actions()
    for permission in MANAGER_PERMISSIONS:
        PermissionManager.grant_permission(int(role.id), permission)

    return create_access_token(
        user_id=int(user.id),
        email=str(user.email),
        roles=[str(role.name)],
        org_id=int(user.o_id),
    )


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_rule(client: TestClient, token: str, rule: dict[str, Any]) -> int:
    response = client.post(
        "/api/v2/rules",
        headers=_auth(token),
        json={
            "rid": rule["rid"],
            "description": rule["description"],
            "logic": rule["logic"],
            "evaluation_lane": rule.get("evaluation_lane", "main"),
            **({"execution_order": rule["execution_order"]} if "execution_order" in rule else {}),
        },
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["success"] is True
    assert payload["rule"]["status"] == "draft"
    return int(payload["rule"]["r_id"])


def _promote_rule(client: TestClient, token: str, rule_id: int) -> None:
    response = client.post(f"/api/v2/rules/{rule_id}/promote", headers=_auth(token))
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["rule"]["status"] == "active"


def _evaluate(client: TestClient, api_key: str, probe: dict[str, Any]) -> dict[str, Any]:
    response = client.post(
        "/api/v2/evaluate",
        headers={"X-API-Key": api_key},
        json={
            "transaction_id": probe["transaction_id"],
            "effective_at": probe["effective_at"],
            "event_data": probe["event_data"],
        },
    )
    assert response.status_code == 200
    return response.json()


def _expected_rule_results(expected: dict[str, str], rule_ids: dict[str, int]) -> dict[str, str]:
    return {str(rule_ids[ref]): outcome for ref, outcome in expected.items()}


def _assert_evaluation(payload: dict[str, Any], probe: dict[str, Any], rule_ids: dict[str, int]) -> None:
    expected = probe["expected"]
    assert payload["resolved_outcome"] == expected["resolved_outcome"]
    assert payload["outcome_counters"] == expected["outcome_counters"]
    assert payload["rule_results"] == _expected_rule_results(expected["rule_results"], rule_ids)


def _assert_history_actions(session, rule_id: int, expected_actions: list[str]) -> None:
    actions = [
        action
        for (action,) in session.query(RuleHistory.action)
        .filter(RuleHistory.r_id == rule_id)
        .order_by(RuleHistory.changed.asc())
        .all()
    ]
    assert actions == expected_actions


def _assert_history_statuses(client: TestClient, token: str, rule_id: int, expected_statuses: list[str]) -> None:
    response = client.get(f"/api/v2/rules/{rule_id}/history", headers=_auth(token))
    assert response.status_code == 200
    assert [entry["status"] for entry in response.json()["history"]] == expected_statuses


def _run_rule_lifecycle_scenario(
    session,
    client: TestClient,
    token: str,
    live_api_key: str,
    scenario: dict[str, Any],
) -> None:
    rule_ids = {scenario["rule"]["ref"]: _create_rule(client, token, scenario["rule"])}
    rule_id = rule_ids[scenario["rule"]["ref"]]
    _promote_rule(client, token, rule_id)

    if "probes" in scenario:
        _assert_evaluation(
            _evaluate(client, live_api_key, scenario["probes"]["active"]), scenario["probes"]["active"], rule_ids
        )

        pause = client.post(f"/api/v2/rules/{rule_id}/pause", headers=_auth(token))
        assert pause.status_code == 200
        assert pause.json()["rule"]["status"] == "paused"
        _assert_evaluation(
            _evaluate(client, live_api_key, scenario["probes"]["paused"]), scenario["probes"]["paused"], rule_ids
        )

        resume = client.post(f"/api/v2/rules/{rule_id}/resume", headers=_auth(token))
        assert resume.status_code == 200
        assert resume.json()["rule"]["status"] == "active"
        _assert_evaluation(
            _evaluate(client, live_api_key, scenario["probes"]["resumed"]), scenario["probes"]["resumed"], rule_ids
        )
    else:
        _assert_evaluation(
            _evaluate(client, live_api_key, scenario["initial_probe"]), scenario["initial_probe"], rule_ids
        )
        update = client.put(f"/api/v2/rules/{rule_id}", headers=_auth(token), json=scenario["update"])
        assert update.status_code == 200
        assert update.json()["rule"]["status"] == "draft"
        _assert_evaluation(_evaluate(client, live_api_key, scenario["draft_probe"]), scenario["draft_probe"], rule_ids)
        _promote_rule(client, token, rule_id)
        _assert_evaluation(
            _evaluate(client, live_api_key, scenario["promoted_probe"]), scenario["promoted_probe"], rule_ids
        )
        _assert_history_statuses(client, token, rule_id, scenario["expected_history_statuses"])

    _assert_history_actions(session, rule_id, scenario["expected_history_actions"])


def _run_shadow_rollout_scenario(
    session,
    client: TestClient,
    token: str,
    live_api_key: str,
    scenario: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rule_ids = {scenario["rule"]["ref"]: _create_rule(client, token, scenario["rule"])}
    rule_id = rule_ids[scenario["rule"]["ref"]]
    _promote_rule(client, token, rule_id)

    if scenario["mode"] == "shadow":
        fake_redis = FakeRedis()
        monkeypatch.setattr(shadow_evaluation_queue, "get_shadow_evaluation_queue_client", lambda: fake_redis)
        deploy = client.post(f"/api/v2/rules/{rule_id}/shadow", headers=_auth(token), json=scenario["candidate"])
        assert deploy.status_code == 200
        payload = _evaluate(client, live_api_key, scenario["evaluation"])
        drain = shadow_evaluation_queue.drain_shadow_evaluation_queue(batch_size=10, max_batches=1)
        assert drain["drained_messages"] == 1
    else:
        deploy = client.post(f"/api/v2/rules/{rule_id}/rollout", headers=_auth(token), json=scenario["candidate"])
        assert deploy.status_code == 200
        payload = _evaluate(client, live_api_key, scenario["evaluation"])
        stored_rule = session.query(RuleModel).filter(RuleModel.r_id == rule_id).one()
        assert stored_rule.logic == scenario["expected_stored_logic"]

    _assert_evaluation(payload, scenario["evaluation"], rule_ids)
    expected_log = scenario["expected_log"]
    log = (
        session.query(RuleDeploymentResultsLog)
        .filter(
            RuleDeploymentResultsLog.ed_id == int(payload["evaluation_id"]), RuleDeploymentResultsLog.r_id == rule_id
        )
        .one()
    )
    for field_name, expected_value in expected_log.items():
        assert getattr(log, field_name) == expected_value


def _run_labels_audit_scenario(
    session,
    client: TestClient,
    token: str,
    live_api_key: str,
    scenario: dict[str, Any],
) -> None:
    org = session.query(Organisation).one()
    rule_ids = {scenario["rule"]["ref"]: _create_rule(client, token, scenario["rule"])}
    rule_id = rule_ids[scenario["rule"]["ref"]]
    _promote_rule(client, token, rule_id)

    label_response = client.post("/api/v2/labels", headers=_auth(token), json={"label_name": scenario["label"]["name"]})
    assert label_response.status_code == 201
    label_name = label_response.json()["label"]["label"]
    assert label_name == scenario["quality_pair"]["label"]
    session.add(
        RuleQualityPair(
            outcome=scenario["quality_pair"]["outcome"],
            label=label_name,
            active=True,
            created_by=scenario["actor"]["email"],
            o_id=int(org.o_id),
        )
    )
    session.commit()

    for event in scenario["events"]:
        payload = _evaluate(client, live_api_key, event)
        assert payload["resolved_outcome"] == "HOLD"
        assert payload["rule_results"] == {str(rule_id): "HOLD"}
        if event.get("assign_label"):
            mark = client.post(
                "/api/v2/labels/mark-event",
                headers=_auth(token),
                json={"transaction_id": event["transaction_id"], "label_name": label_name},
            )
            assert mark.status_code == 200
            assert mark.json()["success"] is True

    quality = client.get("/api/v2/analytics/rule-quality", headers=_auth(token))
    assert quality.status_code == 200
    quality_payload = quality.json()
    assert quality_payload["total_labeled_events"] == scenario["expected_quality"]["total_labeled_events"]
    metric = next(
        item
        for item in quality_payload["pair_metrics"]
        if item["r_id"] == rule_id
        and item["outcome"] == scenario["quality_pair"]["outcome"]
        and item["label"] == label_name
    )
    for field_name, expected_value in scenario["expected_quality"].items():
        if field_name != "total_labeled_events":
            assert metric[field_name] == pytest.approx(expected_value)

    label_audit = client.get("/api/v2/audit/labels", headers=_auth(token))
    assert label_audit.status_code == 200
    assert [item["action"] for item in label_audit.json()["items"][:3]] == scenario["expected_audit_actions"]

    label = session.query(Label).filter(Label.o_id == int(org.o_id), Label.label == label_name).one()
    labeled_events = (
        session.query(EventVersionLabel)
        .filter(EventVersionLabel.o_id == int(org.o_id), EventVersionLabel.el_id == int(label.el_id))
        .count()
    )
    assert labeled_events == scenario["expected_quality"]["total_labeled_events"]


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _hash_payload(event_data: dict[str, Any]) -> str:
    serialized = json.dumps(event_data, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _add_graph_event(session, org_id: int, event: dict[str, Any]) -> EventVersion:
    latest = (
        session.query(EventVersion)
        .filter(EventVersion.o_id == org_id, EventVersion.transaction_id == event["transaction_id"])
        .order_by(EventVersion.event_version.desc(), EventVersion.ev_id.desc())
        .first()
    )
    event_version_number = 1 if latest is None else int(latest.event_version) + 1
    effective_at = _parse_datetime(event["effective_at"])
    event_version = EventVersion(
        o_id=org_id,
        transaction_id=event["transaction_id"],
        event_version=event_version_number,
        effective_at=effective_at,
        observed_at=effective_at,
        event_data=event["event_data"],
        payload_hash=_hash_payload(event["event_data"]),
        terminal_state=False,
        supersedes_ev_id=None if latest is None else int(latest.ev_id),
    )
    session.add(event_version)
    session.flush()
    persist_graph_links_for_event(session, org_id, event_version)
    session.commit()
    return event_version


def _run_graph_feature_scenario(
    session,
    client: TestClient,
    live_api_key: str,
    scenario: dict[str, Any],
) -> None:
    org = session.query(Organisation).one()
    org_id = int(org.o_id)
    for field in scenario["graph_entity_fields"]:
        session.add(GraphEntityField(o_id=org_id, field_path=field["field_path"], entity_type=field["entity_type"]))
    feature = scenario["feature"]
    session.add(
        FeatureDefinition(
            o_id=org_id,
            name=feature["name"],
            entity=feature["entity"],
            feature_name=feature["feature_name"],
            feature_kind=feature["feature_kind"],
            entity_key=feature["entity_key"],
            aggregation_type=feature["aggregation_type"],
            source_field=feature.get("source_field"),
            window_seconds=feature["window_seconds"],
            filters=feature.get("filters") or [],
            graph_config=feature["graph_config"],
            status=feature["status"],
        )
    )
    session.commit()

    for event in scenario["history"]:
        _add_graph_event(session, org_id, event)

    rule = scenario["rule"]
    session.add(
        RuleModel(
            r_id=int(rule["numeric_id"]),
            rid=rule["rid"],
            logic=rule["logic"],
            description=rule["description"],
            o_id=org_id,
        )
    )
    session.commit()
    RDBRuleEngineConfigProducer(db=session, o_id=org_id).save_config(RDBRuleManager(db=session, o_id=org_id))

    rule_ids = {rule["ref"]: int(rule["numeric_id"])}
    payload = _evaluate(client, live_api_key, scenario["evaluation"])
    _assert_evaluation(payload, scenario["evaluation"], rule_ids)
    assert (
        session.query(GraphEventEntityLink).filter(GraphEventEntityLink.o_id == org_id).count()
        == scenario["expected_graph_links"]
    )


def _run_backtesting_scenario(
    session,
    client: TestClient,
    token: str,
    live_api_key: str,
    scenario: dict[str, Any],
) -> None:
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True
    rule_id = _create_rule(client, token, scenario["rule"])
    _promote_rule(client, token, rule_id)

    for event in scenario["history"]:
        payload = _evaluate(client, live_api_key, event)
        assert payload["evaluation_status"] == "new"

    response = client.post(
        "/api/v2/backtesting",
        headers=_auth(token),
        json={"r_id": rule_id, "new_rule_logic": scenario["proposed_logic"]},
    )
    assert response.status_code == 200
    task_id = response.json()["task_id"]

    task_response = client.get(f"/api/v2/backtesting/task/{task_id}", headers=_auth(token))
    assert task_response.status_code == 200
    task_payload = task_response.json()
    expected = scenario["expected_result"]
    assert task_payload["queue_status"] == expected["queue_status"]
    assert task_payload["total_records"] == expected["total_records"]
    assert task_payload["eligible_records"] == expected["eligible_records"]
    assert task_payload["skipped_records"] == expected["skipped_records"]
    assert task_payload["stored_result"] == expected["stored_result"]
    assert task_payload["proposed_result"] == expected["proposed_result"]

    stored_result = session.query(RuleBackTestingResult).filter(RuleBackTestingResult.task_id == task_id).one()
    assert stored_result.result_metrics["stored_result"] == expected["stored_result"]
    assert stored_result.result_metrics["proposed_result"] == expected["proposed_result"]


@pytest.mark.parametrize("suite_and_scenario", SCENARIOS, ids=_scenario_id)
def test_canonical_management_business_scenario_fixtures(
    session,
    live_api_key,
    suite_and_scenario: tuple[dict[str, Any], dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
):
    suite, scenario = suite_and_scenario
    assert suite["version"] == 1
    org = session.query(Organisation).one()
    _seed_outcomes(session, suite, org_id=int(org.o_id))
    token = _manager_token(session, email=scenario.get("actor", {}).get("email", "canonical-manager@example.com"))

    with TestClient(app) as client:
        suite_name = suite["name"]
        if suite_name == "canonical_rule_lifecycle_scenarios":
            _run_rule_lifecycle_scenario(session, client, token, live_api_key, scenario)
        elif suite_name == "canonical_shadow_rollout_scenarios":
            _run_shadow_rollout_scenario(session, client, token, live_api_key, scenario, monkeypatch)
        elif suite_name == "canonical_labels_audit_scenarios":
            _run_labels_audit_scenario(session, client, token, live_api_key, scenario)
        elif suite_name == "canonical_graph_feature_scenarios":
            _run_graph_feature_scenario(session, client, live_api_key, scenario)
        elif suite_name == "canonical_backtesting_scenarios":
            _run_backtesting_scenario(session, client, token, live_api_key, scenario)
        else:
            raise AssertionError(f"Unhandled canonical scenario suite: {suite_name}")
