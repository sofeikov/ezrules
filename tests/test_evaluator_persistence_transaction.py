from types import SimpleNamespace

from sqlalchemy import event as sqlalchemy_event

from ezrules.backend.data_utils import Event, eval_and_store
from ezrules.models import backend_core


def _build_response(rule_id: int, outcome: str = "HOLD") -> dict:
    return {
        "rule_results": {rule_id: outcome},
        "outcome_counters": {outcome: 1},
        "outcome_set": [outcome],
    }


def _track_commit_events(session):
    commit_events: list[str] = []

    def _on_after_commit(_session) -> None:
        commit_events.append("commit")

    sqlalchemy_event.listen(session, "after_commit", _on_after_commit)
    return commit_events, _on_after_commit


def test_eval_and_store_commits_once_for_parent_and_results(session):
    org = session.query(backend_core.Organisation).one()
    rule = backend_core.Rule(
        logic="return !HOLD",
        description="Always hold",
        rid="EVAL_TXN:001",
        o_id=org.o_id,
        r_id=9301,
    )
    session.add(rule)
    session.commit()

    lre = SimpleNamespace(db=session, o_id=org.o_id)
    commit_events, commit_listener = _track_commit_events(session)
    try:
        response, tl_id = eval_and_store(
            lre,
            Event(
                event_id="txn-single-commit",
                event_timestamp=1700000300,
                event_data={"amount": 100},
            ),
            response=_build_response(rule.r_id),
            commit=True,
        )
    finally:
        sqlalchemy_event.remove(session, "after_commit", commit_listener)

    assert commit_events == ["commit"]
    assert response["resolved_outcome"] == "HOLD"

    stored_event = (
        session.query(backend_core.TestingRecordLog).filter(backend_core.TestingRecordLog.tl_id == tl_id).one()
    )
    stored_results = (
        session.query(backend_core.TestingResultsLog).filter(backend_core.TestingResultsLog.tl_id == tl_id).all()
    )

    assert stored_event.event_id == "txn-single-commit"
    assert stored_event.outcome_counters == {"HOLD": 1}
    assert stored_event.resolved_outcome == "HOLD"
    assert [(result.r_id, result.rule_result) for result in stored_results] == [(rule.r_id, "HOLD")]


def test_eval_and_store_preserves_caller_commit_control(session):
    org = session.query(backend_core.Organisation).one()
    rule = backend_core.Rule(
        logic="return !HOLD",
        description="Always hold",
        rid="EVAL_TXN:002",
        o_id=org.o_id,
        r_id=9302,
    )
    session.add(rule)
    session.commit()

    lre = SimpleNamespace(db=session, o_id=org.o_id)
    commit_events, commit_listener = _track_commit_events(session)
    try:
        response, tl_id = eval_and_store(
            lre,
            Event(
                event_id="txn-deferred-commit",
                event_timestamp=1700000301,
                event_data={"amount": 200},
            ),
            response=_build_response(rule.r_id),
            commit=False,
        )
        assert commit_events == []
        assert tl_id is not None

        session.commit()
    finally:
        sqlalchemy_event.remove(session, "after_commit", commit_listener)

    assert commit_events == ["commit"]
    assert response["resolved_outcome"] == "HOLD"

    stored_event = (
        session.query(backend_core.TestingRecordLog).filter(backend_core.TestingRecordLog.tl_id == tl_id).one()
    )
    stored_results = (
        session.query(backend_core.TestingResultsLog).filter(backend_core.TestingResultsLog.tl_id == tl_id).all()
    )

    assert stored_event.event_id == "txn-deferred-commit"
    assert stored_event.outcome_counters == {"HOLD": 1}
    assert stored_event.resolved_outcome == "HOLD"
    assert [(result.r_id, result.rule_result) for result in stored_results] == [(rule.r_id, "HOLD")]
