from pathlib import Path
from typing import Any

import pytest
import yaml
from fastapi.testclient import TestClient

from ezrules.backend.api_v2.main import app
from ezrules.backend.api_v2.routes import evaluator as evaluator_router
from ezrules.backend.runtime_settings import set_runtime_setting
from ezrules.core.rule_updater import RDBRuleEngineConfigProducer, RDBRuleManager
from ezrules.models.backend_core import (
    AllowedOutcome,
    EvaluationDecision,
    EvaluationRuleResult,
    EventVersion,
    Organisation,
    RuleStatus,
    TransactionCurrentVersion,
    UserList,
    UserListEntry,
)
from ezrules.models.backend_core import Rule as RuleModel


UNIVERSE_PATH = Path(__file__).with_name("canonical_evaluation_universe.yaml")


def _load_universe() -> dict[str, Any]:
    with UNIVERSE_PATH.open() as file:
        return yaml.safe_load(file)


UNIVERSE = _load_universe()
RULE_ID_BY_RID = {rule["id"]: int(rule["numeric_id"]) for rule in UNIVERSE["rules"]}


def _scenario_ids() -> list[str]:
    return [scenario["id"] for scenario in UNIVERSE["scenarios"]]


def _seed_outcomes(session, *, org_id: int) -> None:
    session.query(AllowedOutcome).filter(AllowedOutcome.o_id == org_id).delete(synchronize_session=False)
    for outcome in UNIVERSE["outcomes"]:
        session.add(
            AllowedOutcome(
                outcome_name=str(outcome["name"]),
                severity_rank=int(outcome["severity_rank"]),
                o_id=org_id,
            )
        )


def _seed_user_lists(session, *, org_id: int) -> None:
    for list_name, entries in UNIVERSE["user_lists"].items():
        user_list = UserList(list_name=str(list_name), o_id=org_id)
        session.add(user_list)
        session.flush()
        for entry in entries:
            session.add(UserListEntry(entry_value=str(entry), ul_id=int(user_list.ul_id)))


def _seed_rules(session, *, org_id: int) -> None:
    for rule in UNIVERSE["rules"]:
        session.add(
            RuleModel(
                r_id=int(rule["numeric_id"]),
                rid=str(rule["id"]),
                logic=str(rule["logic"]),
                description=str(rule["description"]),
                execution_order=int(rule["order"]),
                evaluation_lane=str(rule["lane"]),
                status=RuleStatus.ACTIVE,
                o_id=org_id,
            )
        )


def _apply_settings(session, *, org_id: int, scenario: dict[str, Any]) -> None:
    settings = dict(UNIVERSE.get("settings") or {})
    settings.update(scenario.get("settings") or {})
    for key, value in settings.items():
        set_runtime_setting(session, str(key), value, org_id)


def _seed_universe(session, scenario: dict[str, Any]) -> int:
    org = session.query(Organisation).one()
    org_id = int(org.o_id)
    _seed_outcomes(session, org_id=org_id)
    _seed_user_lists(session, org_id=org_id)
    _seed_rules(session, org_id=org_id)
    _apply_settings(session, org_id=org_id, scenario=scenario)
    session.commit()

    RDBRuleEngineConfigProducer(db=session, o_id=org_id).save_config(RDBRuleManager(db=session, o_id=org_id))
    return org_id


def _reset_evaluator_state() -> None:
    evaluator_router._lre = None
    evaluator_router._shadow_lre = None
    evaluator_router._allowlist_lre = None


def _expected_rule_results_by_numeric_id(expected: dict[str, str]) -> dict[str, str]:
    return {str(RULE_ID_BY_RID[rid]): outcome for rid, outcome in expected.items()}


def _assert_response_matches(
    response: dict[str, Any], expected: dict[str, Any], prior_responses: list[dict[str, Any]]
) -> None:
    assert response["evaluation_status"] == expected["evaluation_status"]
    assert response["event_version"] == expected["event_version"]
    assert response["is_current"] is expected.get("is_current")
    assert response["resolved_outcome"] == expected["resolved_outcome"]
    assert response["outcome_counters"] == expected["outcome_counters"]
    assert response["rule_results"] == _expected_rule_results_by_numeric_id(expected["rule_results"])

    if "same_evaluation_as_submission" in expected:
        previous = prior_responses[int(expected["same_evaluation_as_submission"])]
        assert response["evaluation_id"] == previous["evaluation_id"]

    for rid in expected.get("absent_rule_results") or []:
        assert str(RULE_ID_BY_RID[rid]) not in response["rule_results"]


def _assert_persisted_rule_results(session, decision: EvaluationDecision, expected: dict[str, Any]) -> None:
    stored_results = (
        session.query(EvaluationRuleResult)
        .filter(EvaluationRuleResult.ed_id == int(decision.ed_id))
        .order_by(EvaluationRuleResult.r_id.asc())
        .all()
    )
    assert {
        str(result.r_id): str(result.rule_result) for result in stored_results
    } == _expected_rule_results_by_numeric_id(expected["rule_results"])

    all_rule_results = {str(key): value for key, value in (decision.all_rule_results or {}).items()}
    for rid in expected.get("absent_rule_results") or []:
        assert str(RULE_ID_BY_RID[rid]) not in all_rule_results


def _assert_submission_persisted(session, submission: dict[str, Any], response: dict[str, Any]) -> None:
    if submission["expected"]["evaluation_status"] == "duplicate":
        return

    decision = (
        session.query(EvaluationDecision).filter(EvaluationDecision.ed_id == int(response["evaluation_id"])).one()
    )
    assert decision.transaction_id == submission["transaction_id"]
    assert int(decision.event_version) == submission["expected"]["event_version"]
    assert decision.outcome_counters == submission["expected"]["outcome_counters"]
    assert decision.resolved_outcome == submission["expected"]["resolved_outcome"]
    assert bool(decision.is_current) is submission["expected"]["is_current"]
    assert decision.rule_config_label == "production"
    _assert_persisted_rule_results(session, decision, submission["expected"])


def _assert_final_projection(session, *, org_id: int, scenario: dict[str, Any]) -> None:
    final = scenario["final"]
    transaction_id = scenario["submissions"][-1]["transaction_id"]
    assert (
        session.query(EventVersion)
        .filter(EventVersion.o_id == org_id, EventVersion.transaction_id == transaction_id)
        .count()
        == final["event_versions"]
    )
    assert (
        session.query(EvaluationDecision)
        .filter(EvaluationDecision.o_id == org_id, EvaluationDecision.transaction_id == transaction_id)
        .count()
        == final["decisions"]
    )

    current = (
        session.query(TransactionCurrentVersion)
        .filter(TransactionCurrentVersion.o_id == org_id, TransactionCurrentVersion.transaction_id == transaction_id)
        .one()
    )
    assert current.current_effective_at is not None

    current_decision = (
        session.query(EvaluationDecision)
        .filter(EvaluationDecision.o_id == org_id, EvaluationDecision.ed_id == int(current.current_ed_id))
        .one()
    )
    assert int(current_decision.event_version) == final["current_event_version"]
    assert current_decision.resolved_outcome == final["current_resolved_outcome"]

    superseded_versions = set(final.get("superseded_decision_versions") or [])
    if superseded_versions:
        superseded = (
            session.query(EvaluationDecision)
            .filter(
                EvaluationDecision.o_id == org_id,
                EvaluationDecision.transaction_id == transaction_id,
                EvaluationDecision.is_current.is_(False),
            )
            .all()
        )
        assert {int(decision.event_version) for decision in superseded} == superseded_versions


def test_canonical_evaluation_universe_is_internally_consistent():
    assert UNIVERSE["version"] == 1
    assert len(RULE_ID_BY_RID) == len(UNIVERSE["rules"])
    assert len(set(RULE_ID_BY_RID.values())) == len(UNIVERSE["rules"])
    assert len(_scenario_ids()) == len(set(_scenario_ids()))
    assert [outcome["severity_rank"] for outcome in UNIVERSE["outcomes"]] == sorted(
        outcome["severity_rank"] for outcome in UNIVERSE["outcomes"]
    )


@pytest.mark.parametrize("scenario", UNIVERSE["scenarios"], ids=_scenario_ids())
def test_canonical_evaluation_business_journey(session, live_api_key, scenario):
    org_id = _seed_universe(session, scenario)
    _reset_evaluator_state()
    prior_responses: list[dict[str, Any]] = []

    try:
        with TestClient(app) as client:
            for submission in scenario["submissions"]:
                result = client.post(
                    "/api/v2/evaluate",
                    json={
                        "transaction_id": submission["transaction_id"],
                        "effective_at": submission["effective_at"],
                        "event_data": submission["event_data"],
                    },
                    headers={"X-API-Key": live_api_key},
                )

                assert result.status_code == 200
                payload = result.json()
                _assert_response_matches(payload, submission["expected"], prior_responses)
                _assert_submission_persisted(session, submission, payload)
                prior_responses.append(payload)
    finally:
        _reset_evaluator_state()

    _assert_final_projection(session, org_id=org_id, scenario=scenario)
