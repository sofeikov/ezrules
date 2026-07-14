import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import pytest
from fastapi.testclient import TestClient

from ezrules.backend import shadow_evaluation_queue
from ezrules.backend.agent_tools import NO_OUTCOME, replay_rule_change
from ezrules.backend.api_v2.auth.jwt import create_access_token
from ezrules.backend.api_v2.main import app
from ezrules.backend.api_v2.routes import evaluator as evaluator_router
from ezrules.backend.backtesting import BacktestRecord, compute_backtest_metrics
from ezrules.backend.features import FeatureResolver
from ezrules.backend.rule_executors.executors import LocalRuleExecutorSQL
from ezrules.core.permissions import PermissionManager
from ezrules.core.permissions_constants import PermissionAction
from ezrules.core.rule import Rule
from ezrules.core.rule_updater import (
    RDBRuleEngineConfigProducer,
    RDBRuleManager,
    deploy_rule_to_rollout,
    deploy_rule_to_shadow,
    remove_rule_from_shadow,
)
from ezrules.core.type_casting import FieldCastConfig, FieldType
from ezrules.core.user_lists import PersistentUserListManager
from ezrules.models.backend_core import (
    AllowedOutcome,
    EventVersion,
    FeatureDefinition,
    FieldTypeConfig,
    Organisation,
    Role,
    RuleDeploymentResultsLog,
    RuleStatus,
    User,
)
from ezrules.models.backend_core import Rule as RuleModel
from tests.canonical_helpers import _hash_payload

AMOUNT_RULE_ID = 9601
AMOUNT_RULE_LOGIC = "if $amount >= 100:\n\treturn !REVIEW"
FEATURE_RULE_ID = 9602
FEATURE_RULE_LOGIC = "if $amount >= 100 and stat[sender.sent_amount_sum_24h] >= 100:\n\treturn !ESCALATE"


@dataclass(frozen=True, slots=True)
class RuleContract:
    r_id: int
    rid: str
    logic: str
    outcome: str


RULE_CONTRACTS = (
    RuleContract(
        r_id=AMOUNT_RULE_ID,
        rid="surface_parity_amount_review",
        logic=AMOUNT_RULE_LOGIC,
        outcome="REVIEW",
    ),
    RuleContract(
        r_id=FEATURE_RULE_ID,
        rid="surface_parity_sender_escalation",
        logic=FEATURE_RULE_LOGIC,
        outcome="ESCALATE",
    ),
)


@dataclass(frozen=True, slots=True)
class ParityScenario:
    name: str
    transaction_id: str
    raw_event: dict[str, Any]
    expected_rule_results: dict[int, str]
    expected_resolved_outcome: str | None


SCENARIOS = (
    ParityScenario(
        name="cast-string-and-match",
        transaction_id="parity-match",
        raw_event={"amount": "125", "sender_id": "S1"},
        expected_rule_results={AMOUNT_RULE_ID: "REVIEW", FEATURE_RULE_ID: "ESCALATE"},
        expected_resolved_outcome="ESCALATE",
    ),
    ParityScenario(
        name="cast-string-and-no-match",
        transaction_id="parity-no-match",
        raw_event={"amount": "75", "sender_id": "S1"},
        expected_rule_results={},
        expected_resolved_outcome=None,
    ),
)


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
        return [queue.pop() for _ in range(min(count, len(queue)))]

    def lock(self, name: str, timeout: int | None = None, blocking: bool = False) -> FakeRedisLock:
        del timeout, blocking
        return FakeRedisLock(self._lock_state, name)


def _manager_token(session, *, org_id: int) -> str:
    role = Role(name="surface_parity_manager", description="Surface parity manager", o_id=org_id)
    user = User(
        email="surface-parity@example.com",
        password=bcrypt.hashpw(b"surface-parity", bcrypt.gensalt()).decode("utf-8"),
        active=True,
        fs_uniquifier="surface-parity@example.com",
        o_id=org_id,
    )
    user.roles.append(role)
    session.add_all([role, user])
    session.commit()

    PermissionManager.db_session = session
    PermissionManager.init_default_actions()
    PermissionManager.grant_permission(int(role.id), PermissionAction.VIEW_RULES)
    PermissionManager.grant_permission(int(role.id), PermissionAction.SUBMIT_TEST_EVENTS)

    return create_access_token(
        user_id=int(user.id),
        email=str(user.email),
        roles=[str(role.name)],
        org_id=org_id,
    )


def _seed_surface_contract(session) -> tuple[int, list[RuleModel], str, datetime]:
    org = session.query(Organisation).one()
    org_id = int(org.o_id)
    session.add(AllowedOutcome(outcome_name="ESCALATE", severity_rank=1, o_id=org_id))
    session.add(AllowedOutcome(outcome_name="REVIEW", severity_rank=2, o_id=org_id))
    session.add(FieldTypeConfig(field_name="amount", configured_type="integer", o_id=org_id))
    session.add(
        FeatureDefinition(
            o_id=org_id,
            name="Sender sent amount 24h",
            entity="sender",
            feature_name="sent_amount_sum_24h",
            entity_key="sender_id",
            aggregation_type="sum",
            source_field="amount",
            window_seconds=86400,
            filters=[],
            status="active",
        )
    )
    as_of = datetime.now(UTC).replace(microsecond=0)
    prior_event_data = {"amount": 110, "sender_id": "S1"}
    session.add(
        EventVersion(
            o_id=org_id,
            transaction_id="parity-prior-volume",
            event_version=1,
            effective_at=as_of - timedelta(hours=1),
            observed_at=as_of - timedelta(hours=1),
            event_data=prior_event_data,
            payload_hash=_hash_payload(prior_event_data),
        )
    )
    rule_models = [
        RuleModel(
            r_id=contract.r_id,
            rid=contract.rid,
            logic=contract.logic,
            description=f"Parity contract for {contract.rid}",
            execution_order=execution_order,
            evaluation_lane="main",
            status=RuleStatus.ACTIVE,
            o_id=org_id,
        )
        for execution_order, contract in enumerate(RULE_CONTRACTS, start=1)
    ]
    session.add_all(rule_models)
    session.commit()

    RDBRuleEngineConfigProducer(db=session, o_id=org_id).save_config(RDBRuleManager(db=session, o_id=org_id))
    return org_id, rule_models, _manager_token(session, org_id=org_id), as_of


def _serialized_rule_results(rule_results: dict[int, str]) -> dict[str, str]:
    return {str(rule_id): outcome for rule_id, outcome in rule_results.items()}


def _authenticate(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _reset_evaluator_state() -> None:
    evaluator_router._lre = None
    evaluator_router._shadow_lre = None
    evaluator_router._allowlist_lre = None


def _set_evaluator_state(session, *, org_id: int) -> None:
    evaluator_router._lre = LocalRuleExecutorSQL(db=session, o_id=org_id)
    evaluator_router._allowlist_lre = LocalRuleExecutorSQL(db=session, o_id=org_id, label="allowlist")


def _deploy_shadow_contract(session, *, org_id: int, rule_models: list[RuleModel]) -> None:
    for rule_model, contract in zip(rule_models, RULE_CONTRACTS, strict=True):
        deploy_rule_to_shadow(
            db=session,
            o_id=org_id,
            rule_model=rule_model,
            changed_by="surface-parity@example.com",
            logic_override=contract.logic,
        )


def _deploy_rollout_contract(session, *, org_id: int, rule_models: list[RuleModel]) -> None:
    for rule_model, contract in zip(rule_models, RULE_CONTRACTS, strict=True):
        remove_rule_from_shadow(
            db=session,
            o_id=org_id,
            r_id=int(rule_model.r_id),
            changed_by="surface-parity@example.com",
        )
        deploy_rule_to_rollout(
            db=session,
            o_id=org_id,
            rule_model=rule_model,
            traffic_percent=100,
            changed_by="surface-parity@example.com",
            logic_override=contract.logic,
        )


def test_rule_decisions_match_across_all_execution_surfaces(session, live_api_key, monkeypatch):
    org_id, rule_models, token, as_of = _seed_surface_contract(session)
    fake_redis = FakeRedis()
    monkeypatch.setattr(shadow_evaluation_queue, "get_shadow_evaluation_queue_client", lambda: fake_redis)
    _deploy_shadow_contract(session, org_id=org_id, rule_models=rule_models)
    _set_evaluator_state(session, org_id=org_id)
    shadow_payloads: dict[str, dict[str, Any]] = {}

    try:
        with TestClient(app) as client:
            for scenario in SCENARIOS:
                for contract in RULE_CONTRACTS:
                    rule_test = client.post(
                        "/api/v2/rules/test",
                        headers=_authenticate(token),
                        json={"rule_source": contract.logic, "test_json": json.dumps(scenario.raw_event)},
                    )
                    assert rule_test.status_code == 200
                    assert rule_test.json()["status"] == "ok"
                    assert rule_test.json()["rule_outcome"] == scenario.expected_rule_results.get(contract.r_id)

                request_body = {
                    "transaction_id": f"shadow-{scenario.transaction_id}",
                    "effective_at": as_of.isoformat(),
                    "event_data": scenario.raw_event,
                }
                event_test = client.post(
                    "/api/v2/event-tests",
                    headers=_authenticate(token),
                    json=request_body,
                )
                assert event_test.status_code == 200
                event_test_payload = event_test.json()
                expected_rule_results = _serialized_rule_results(scenario.expected_rule_results)
                assert event_test_payload["resolved_outcome"] == scenario.expected_resolved_outcome
                assert event_test_payload["rule_results"] == expected_rule_results
                assert list(event_test_payload["all_rule_results"]) == [
                    str(contract.r_id) for contract in RULE_CONTRACTS
                ]
                assert [item["r_id"] for item in event_test_payload["evaluated_rules"]] == [
                    contract.r_id for contract in RULE_CONTRACTS
                ]

                live = client.post(
                    "/api/v2/evaluate",
                    headers={"X-API-Key": live_api_key},
                    json=request_body,
                )
                assert live.status_code == 200
                live_payload = live.json()
                shadow_payloads[scenario.transaction_id] = live_payload
                assert live_payload["resolved_outcome"] == scenario.expected_resolved_outcome
                assert live_payload["rule_results"] == expected_rule_results
                assert list(live_payload["rule_results"]) == list(expected_rule_results)
    finally:
        _reset_evaluator_state()

    drain_result = shadow_evaluation_queue.drain_shadow_evaluation_queue(batch_size=10, max_batches=1)
    assert drain_result["drained_messages"] == len(SCENARIOS)

    for scenario in SCENARIOS:
        decision_id = int(shadow_payloads[scenario.transaction_id]["evaluation_id"])
        for contract in RULE_CONTRACTS:
            expected_outcome = scenario.expected_rule_results.get(contract.r_id)
            shadow_log = (
                session.query(RuleDeploymentResultsLog)
                .filter(
                    RuleDeploymentResultsLog.ed_id == decision_id,
                    RuleDeploymentResultsLog.r_id == contract.r_id,
                    RuleDeploymentResultsLog.mode == "shadow",
                )
                .one()
            )
            assert shadow_log.candidate_result == expected_outcome
            assert shadow_log.control_result == expected_outcome

    _deploy_rollout_contract(session, org_id=org_id, rule_models=rule_models)
    _set_evaluator_state(session, org_id=org_id)
    rollout_payloads: dict[str, dict[str, Any]] = {}
    try:
        with TestClient(app) as client:
            for scenario in SCENARIOS:
                request_body = {
                    "transaction_id": f"rollout-{scenario.transaction_id}",
                    "effective_at": as_of.isoformat(),
                    "event_data": scenario.raw_event,
                }
                event_test = client.post(
                    "/api/v2/event-tests",
                    headers=_authenticate(token),
                    json=request_body,
                )
                assert event_test.status_code == 200
                assert event_test.json()["rule_results"] == _serialized_rule_results(scenario.expected_rule_results)

                live = client.post(
                    "/api/v2/evaluate",
                    headers={"X-API-Key": live_api_key},
                    json=request_body,
                )
                assert live.status_code == 200
                rollout_payloads[scenario.transaction_id] = live.json()
                assert live.json()["resolved_outcome"] == scenario.expected_resolved_outcome
                assert live.json()["rule_results"] == _serialized_rule_results(scenario.expected_rule_results)
    finally:
        _reset_evaluator_state()

    for scenario in SCENARIOS:
        decision_id = int(rollout_payloads[scenario.transaction_id]["evaluation_id"])
        for contract in RULE_CONTRACTS:
            expected_outcome = scenario.expected_rule_results.get(contract.r_id)
            rollout_log = (
                session.query(RuleDeploymentResultsLog)
                .filter(
                    RuleDeploymentResultsLog.ed_id == decision_id,
                    RuleDeploymentResultsLog.r_id == contract.r_id,
                    RuleDeploymentResultsLog.mode == "split",
                )
                .one()
            )
            assert rollout_log.selected_variant == "candidate"
            assert rollout_log.candidate_result == expected_outcome
            assert rollout_log.returned_result == expected_outcome

    list_provider = PersistentUserListManager(session, org_id)
    records = [BacktestRecord(event_data=scenario.raw_event, as_of=as_of) for scenario in SCENARIOS]
    for rule_model, contract in zip(rule_models, RULE_CONTRACTS, strict=True):
        compiled_rule = Rule(
            rid=str(rule_model.rid),
            logic=contract.logic,
            r_id=int(rule_model.r_id),
            list_values_provider=list_provider,
        )
        backtest = compute_backtest_metrics(
            stored_rule=compiled_rule,
            proposed_rule=compiled_rule,
            test_records=records,
            configs=[FieldCastConfig(field_name="amount", field_type=FieldType.INTEGER)],
            feature_resolver=FeatureResolver(session, org_id),
        )
        assert backtest["eligible_records"] == len(SCENARIOS)
        assert backtest["skipped_records"] == 0
        assert backtest["stored_result"] == {contract.outcome: 1}
        assert backtest["proposed_result"] == {contract.outcome: 1}

        replay = replay_rule_change(
            session,
            org_id=org_id,
            rule_model=rule_model,
            proposed_logic=contract.logic,
            lookback_days=3650,
            group_by=[],
            max_records=100,
        )
        replay_by_transaction = {item.record.transaction_id: item for item in replay.evaluations}
        assert replay.eligible_records == 2 * len(SCENARIOS)
        assert replay.skipped_records == 0
        assert replay.stored_counts == {contract.outcome: 2, NO_OUTCOME: 2}
        assert replay.proposed_counts == {contract.outcome: 2, NO_OUTCOME: 2}
        for scenario in SCENARIOS:
            expected_outcome = scenario.expected_rule_results.get(contract.r_id)
            for prefix in ("shadow", "rollout"):
                evaluation = replay_by_transaction[f"{prefix}-{scenario.transaction_id}"]
                assert evaluation.stored_outcome == expected_outcome
                assert evaluation.proposed_outcome == expected_outcome


@pytest.mark.parametrize(
    ("raw_event", "expected_error_fragment"),
    [
        pytest.param({"sender_id": "S1"}, "amount", id="missing-field"),
        pytest.param({"amount": "not-a-number", "sender_id": "S1"}, "cannot cast", id="invalid-cast"),
    ],
)
def test_rule_errors_are_classified_consistently_before_persistence(
    session,
    live_api_key,
    raw_event: dict[str, Any],
    expected_error_fragment: str,
):
    org_id, _rule_models, token, as_of = _seed_surface_contract(session)
    _set_evaluator_state(session, org_id=org_id)
    request_body = {
        "transaction_id": f"parity-error-{expected_error_fragment.replace(' ', '-')}",
        "effective_at": as_of.isoformat(),
        "event_data": raw_event,
    }

    try:
        with TestClient(app) as client:
            rule_test = client.post(
                "/api/v2/rules/test",
                headers=_authenticate(token),
                json={"rule_source": AMOUNT_RULE_LOGIC, "test_json": json.dumps(raw_event)},
            )
            event_test = client.post(
                "/api/v2/event-tests",
                headers=_authenticate(token),
                json=request_body,
            )
            live = client.post(
                "/api/v2/evaluate",
                headers={"X-API-Key": live_api_key},
                json=request_body,
            )
    finally:
        _reset_evaluator_state()

    assert rule_test.status_code == 200
    assert rule_test.json()["status"] == "error"
    assert expected_error_fragment in rule_test.json()["reason"].lower()
    assert event_test.status_code == 400
    assert expected_error_fragment in event_test.json()["detail"].lower()
    assert live.status_code == 400
    assert expected_error_fragment in live.json()["detail"].lower()

    compiled_rule = Rule(
        rid="surface_parity_amount_review",
        logic=AMOUNT_RULE_LOGIC,
        r_id=AMOUNT_RULE_ID,
    )
    backtest = compute_backtest_metrics(
        stored_rule=compiled_rule,
        proposed_rule=compiled_rule,
        test_records=[BacktestRecord(event_data=raw_event, as_of=as_of)],
        configs=[FieldCastConfig(field_name="amount", field_type=FieldType.INTEGER)],
    )
    assert backtest["eligible_records"] == 0
    assert backtest["skipped_records"] == 1
    assert any(expected_error_fragment in warning.lower() for warning in backtest["warnings"])
