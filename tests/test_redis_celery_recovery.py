import hashlib
import json
import os
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime

import pytest
from celery.exceptions import TaskRevokedError
from redis import Redis
from sqlalchemy.orm import Session, sessionmaker

from ezrules.backend import observation_queue
from ezrules.backend.backtesting import BACKTEST_QUEUE_CANCELLED
from ezrules.backend.tasks import (
    app as celery_app,
)
from ezrules.backend.tasks import (
    backtest_rule_change,
    detect_alerts_for_decision_task,
    dispatch_integration_outbox_task,
    drain_field_observation_queue,
    drain_shadow_evaluation_queue_task,
    generate_rule_quality_report,
    process_evaluation_for_cases_task,
    sweep_alert_rules_task,
)
from ezrules.models.backend_core import (
    EvaluationDecision,
    EventVersion,
    FieldObservation,
    Organisation,
    RuleBackTestingResult,
    RuleDeploymentResultsLog,
    RuleQualityReport,
    ShadowResultsLog,
)
from ezrules.models.backend_core import (
    Rule as RuleModel,
)
from ezrules.models.database import engine
from ezrules.settings import app_settings

pytestmark = pytest.mark.skipif(
    os.environ.get("EZRULES_LIVE_REDIS_CELERY_SMOKE") != "true",
    reason="live Redis/Celery recovery tests run only in the dedicated CI lane",
)


RECOVERY_ORG_ID = 1
RECOVERY_RULE_PREFIX = "REDIS_RECOVERY:"
RECOVERY_TRANSACTION_PREFIX = "redis-recovery-"
SessionLocal = sessionmaker(bind=engine)


@contextmanager
def _session_scope() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _processing_key(queue_key: str) -> str:
    return f"{queue_key}:processing"


def _cleanup_database() -> None:
    with _session_scope() as session:
        if session.get(Organisation, RECOVERY_ORG_ID) is None:
            session.add(Organisation(o_id=RECOVERY_ORG_ID, name="Redis Celery Recovery"))
            session.flush()

        recovery_rule_ids = [
            int(row.r_id)
            for row in session.query(RuleModel.r_id).filter(RuleModel.rid.like(f"{RECOVERY_RULE_PREFIX}%")).all()
        ]
        session.query(RuleBackTestingResult).filter(
            RuleBackTestingResult.task_id.like(f"{RECOVERY_TRANSACTION_PREFIX}%")
        ).delete(synchronize_session=False)
        session.query(RuleQualityReport).filter(RuleQualityReport.requested_by == RECOVERY_TRANSACTION_PREFIX).delete(
            synchronize_session=False
        )
        if recovery_rule_ids:
            session.query(RuleDeploymentResultsLog).filter(RuleDeploymentResultsLog.r_id.in_(recovery_rule_ids)).delete(
                synchronize_session=False
            )
            session.query(ShadowResultsLog).filter(ShadowResultsLog.r_id.in_(recovery_rule_ids)).delete(
                synchronize_session=False
            )
        recovery_decisions = session.query(EvaluationDecision).filter(
            EvaluationDecision.transaction_id.like(f"{RECOVERY_TRANSACTION_PREFIX}%")
        )
        recovery_decisions.delete(synchronize_session=False)
        session.query(EventVersion).filter(EventVersion.transaction_id.like(f"{RECOVERY_TRANSACTION_PREFIX}%")).delete(
            synchronize_session=False
        )
        if recovery_rule_ids:
            session.query(RuleModel).filter(RuleModel.r_id.in_(recovery_rule_ids)).delete(synchronize_session=False)
        session.query(FieldObservation).filter(FieldObservation.o_id == RECOVERY_ORG_ID).delete(
            synchronize_session=False
        )


@pytest.fixture(autouse=True)
def reset_recovery_state() -> Iterator[Redis]:
    redis_client = Redis.from_url(app_settings.CELERY_BROKER_URL, decode_responses=True)
    queue_keys = (
        app_settings.OBSERVATION_QUEUE_KEY,
        _processing_key(app_settings.OBSERVATION_QUEUE_KEY),
        app_settings.OBSERVATION_QUEUE_LOCK_KEY,
        app_settings.SHADOW_EVALUATION_QUEUE_KEY,
        _processing_key(app_settings.SHADOW_EVALUATION_QUEUE_KEY),
        app_settings.SHADOW_EVALUATION_QUEUE_LOCK_KEY,
    )
    redis_client.delete(*queue_keys)
    observation_queue.get_observation_queue_client.cache_clear()
    _cleanup_database()

    yield redis_client

    redis_client.delete(*queue_keys)
    observation_queue.get_observation_queue_client.cache_clear()
    _cleanup_database()


def _worker_names() -> set[str]:
    replies = celery_app.control.inspect(timeout=5).registered() or {}
    return set(replies)


def _create_shadow_payload() -> tuple[str, int, int]:
    now = datetime.now(UTC)
    transaction_id = f"{RECOVERY_TRANSACTION_PREFIX}shadow"
    with _session_scope() as session:
        rule = RuleModel(
            rid=f"{RECOVERY_RULE_PREFIX}SHADOW",
            logic="return !HOLD",
            description="Redis recovery shadow rule",
            execution_order=1,
            o_id=RECOVERY_ORG_ID,
        )
        session.add(rule)
        session.flush()
        event_version = EventVersion(
            o_id=RECOVERY_ORG_ID,
            transaction_id=transaction_id,
            event_version=1,
            effective_at=now,
            observed_at=now,
            event_data={"amount": 100},
            payload_hash=hashlib.sha256(b'{"amount":100}').hexdigest(),
        )
        session.add(event_version)
        session.flush()
        decision = EvaluationDecision(
            ev_id=int(event_version.ev_id),
            o_id=RECOVERY_ORG_ID,
            transaction_id=transaction_id,
            event_version=1,
            effective_at=now,
            observed_at=now,
            outcome_counters={},
            all_rule_results={},
        )
        session.add(decision)
        session.flush()
        rule_id = int(rule.r_id)
        decision_id = int(decision.ed_id)

    payload = json.dumps(
        {
            "o_id": RECOVERY_ORG_ID,
            "event_id": transaction_id,
            "event_data": {"amount": 100},
            "evaluation_decision_id": decision_id,
            "event_version_id": None,
            "production_all_rule_results": {str(rule_id): "HOLD"},
            "shadow_config": [
                {
                    "rid": f"{RECOVERY_RULE_PREFIX}SHADOW",
                    "description": "Redis recovery shadow rule",
                    "logic": "return !HOLD",
                    "params": [],
                    "r_id": rule_id,
                }
            ],
            "shadow_config_version": 1,
            "main_rule_execution_mode": "all_matches",
            "enqueued_at": now.isoformat(),
        },
        separators=(",", ":"),
        sort_keys=True,
    )
    return payload, decision_id, rule_id


def test_worker_registry_executes_every_application_task(reset_recovery_state: Redis):
    del reset_recovery_state
    expected_tasks = {
        "ezrules.backend.tasks.backtest_rule_change",
        "ezrules.backend.tasks.generate_rule_quality_report",
        "ezrules.backend.tasks.drain_field_observation_queue",
        "ezrules.backend.tasks.drain_shadow_evaluation_queue_task",
        "ezrules.backend.tasks.detect_alerts_for_decision_task",
        "ezrules.backend.tasks.process_evaluation_for_cases_task",
        "ezrules.backend.tasks.dispatch_integration_outbox_task",
        "ezrules.backend.tasks.sweep_alert_rules_task",
    }
    assert len(_worker_names()) >= 2

    registered = celery_app.control.inspect(timeout=5).registered() or {}
    for tasks in registered.values():
        assert expected_tasks <= set(tasks)

    results = {
        "backtest": backtest_rule_change.apply_async(args=[999_999, "return !HOLD", RECOVERY_ORG_ID]).get(timeout=30),
        "quality": generate_rule_quality_report.apply_async(args=[999_999]).get(timeout=30),
        "observation": drain_field_observation_queue.apply_async().get(timeout=30),
        "shadow": drain_shadow_evaluation_queue_task.apply_async().get(timeout=30),
        "alert": detect_alerts_for_decision_task.apply_async(args=[RECOVERY_ORG_ID, 999_999]).get(timeout=30),
        "case": process_evaluation_for_cases_task.apply_async(args=[RECOVERY_ORG_ID, 999_999]).get(timeout=30),
        "outbox": dispatch_integration_outbox_task.apply_async().get(timeout=30),
        "sweep": sweep_alert_rules_task.apply_async().get(timeout=30),
    }

    assert results == {
        "backtest": {"error": "Rule with id 999999 not found"},
        "quality": {"error": "Rule quality report 999999 not found"},
        "observation": {"drained_batches": 0, "drained_messages": 0},
        "shadow": {"drained_batches": 0, "drained_messages": 0, "max_enqueue_lag_seconds": 0},
        "alert": {"incidents": 0},
        "case": {"case_id": None, "action": "missing_decision"},
        "outbox": {"delivered": 0, "failed": 0},
        "sweep": {"checked": 0, "incidents": 0},
    }


def test_duplicate_and_orphaned_observations_survive_two_worker_drain(reset_recovery_state: Redis):
    redis_client = reset_recovery_state
    duplicate_event = {"amount": 500, "country": "GB"}
    assert observation_queue.enqueue_observations(duplicate_event, RECOVERY_ORG_ID)
    assert observation_queue.enqueue_observations(duplicate_event, RECOVERY_ORG_ID)
    for amount in range(18):
        assert observation_queue.enqueue_observations({"amount": amount, "country": "GB"}, RECOVERY_ORG_ID)

    processing_key = _processing_key(app_settings.OBSERVATION_QUEUE_KEY)
    assert redis_client.rpoplpush(app_settings.OBSERVATION_QUEUE_KEY, processing_key) is not None

    first = drain_field_observation_queue.apply_async()
    second = drain_field_observation_queue.apply_async()
    drain_results = [first.get(timeout=30), second.get(timeout=30)]

    assert sum(result["drained_messages"] for result in drain_results) == 20
    assert redis_client.llen(app_settings.OBSERVATION_QUEUE_KEY) == 0
    assert redis_client.llen(processing_key) == 0
    with _session_scope() as session:
        observations = (
            session.query(FieldObservation.field_name, FieldObservation.observed_json_type)
            .filter(FieldObservation.o_id == RECOVERY_ORG_ID)
            .order_by(FieldObservation.field_name)
            .all()
        )
    assert observations == [("amount", "int"), ("country", "str")]


def test_observation_failure_rolls_back_and_restores_reserved_message(reset_recovery_state: Redis):
    redis_client = reset_recovery_state
    redis_client.lpush(app_settings.OBSERVATION_QUEUE_KEY, "{not-json")

    result = drain_field_observation_queue.apply_async()
    with pytest.raises(ValueError):
        result.get(timeout=30, propagate=True)

    assert redis_client.lrange(app_settings.OBSERVATION_QUEUE_KEY, 0, -1) == ["{not-json"]
    assert redis_client.llen(_processing_key(app_settings.OBSERVATION_QUEUE_KEY)) == 0


def test_shadow_redelivery_recovers_orphan_without_duplicate_ledgers(reset_recovery_state: Redis):
    redis_client = reset_recovery_state
    payload, decision_id, rule_id = _create_shadow_payload()
    processing_key = _processing_key(app_settings.SHADOW_EVALUATION_QUEUE_KEY)
    redis_client.lpush(app_settings.SHADOW_EVALUATION_QUEUE_KEY, payload)
    assert redis_client.rpoplpush(app_settings.SHADOW_EVALUATION_QUEUE_KEY, processing_key) == payload
    redis_client.lpush(app_settings.SHADOW_EVALUATION_QUEUE_KEY, payload)

    first = drain_shadow_evaluation_queue_task.apply_async()
    second = drain_shadow_evaluation_queue_task.apply_async()
    drain_results = [first.get(timeout=30), second.get(timeout=30)]

    assert sum(result["drained_messages"] for result in drain_results) == 2
    assert redis_client.llen(app_settings.SHADOW_EVALUATION_QUEUE_KEY) == 0
    assert redis_client.llen(processing_key) == 0
    with _session_scope() as session:
        assert (
            session.query(ShadowResultsLog)
            .filter(ShadowResultsLog.ed_id == decision_id, ShadowResultsLog.r_id == rule_id)
            .count()
            == 1
        )
        assert (
            session.query(RuleDeploymentResultsLog)
            .filter(
                RuleDeploymentResultsLog.ed_id == decision_id,
                RuleDeploymentResultsLog.r_id == rule_id,
                RuleDeploymentResultsLog.mode == "shadow",
            )
            .count()
            == 1
        )


def test_cancelled_backtest_is_revoked_by_broker_and_stays_cancelled(reset_recovery_state: Redis):
    del reset_recovery_state
    task_id = f"{RECOVERY_TRANSACTION_PREFIX}cancelled"
    with _session_scope() as session:
        rule = RuleModel(
            rid=f"{RECOVERY_RULE_PREFIX}CANCELLED",
            logic="return !HOLD",
            description="Cancelled recovery backtest",
            o_id=RECOVERY_ORG_ID,
        )
        session.add(rule)
        session.flush()
        session.add(
            RuleBackTestingResult(
                r_id=int(rule.r_id),
                task_id=task_id,
                stored_logic="return !HOLD",
                proposed_logic="return !REVIEW",
                status=BACKTEST_QUEUE_CANCELLED,
                result_metrics={"error": "Backtest cancelled by operator"},
                completed_at=datetime.now(UTC),
            )
        )
        rule_id = int(rule.r_id)

    revoke_replies = celery_app.control.revoke(task_id, terminate=False, reply=True, timeout=5) or []
    assert len(revoke_replies) >= 2
    task_result = backtest_rule_change.apply_async(
        args=[rule_id, "return !REVIEW", RECOVERY_ORG_ID],
        task_id=task_id,
    )
    with pytest.raises(TaskRevokedError):
        task_result.get(timeout=30, propagate=True)

    with _session_scope() as session:
        record = session.query(RuleBackTestingResult).filter(RuleBackTestingResult.task_id == task_id).one()
        assert record.status == BACKTEST_QUEUE_CANCELLED
        assert record.result_metrics == {"error": "Backtest cancelled by operator"}


def test_completed_quality_report_is_not_recomputed_on_redelivery(reset_recovery_state: Redis):
    del reset_recovery_state
    completed_at = datetime.now(UTC)
    with _session_scope() as session:
        report = RuleQualityReport(
            status="SUCCESS",
            min_support=1,
            lookback_days=30,
            freeze_at=completed_at,
            max_decision_id=0,
            pair_set_hash="",
            pair_set=[],
            requested_by=RECOVERY_TRANSACTION_PREFIX,
            result={"sentinel": "already-computed"},
            completed_at=completed_at,
            o_id=RECOVERY_ORG_ID,
        )
        session.add(report)
        session.flush()
        report_id = int(report.rqr_id)

    assert generate_rule_quality_report.apply_async(args=[report_id]).get(timeout=30) == {"status": "SUCCESS"}

    with _session_scope() as session:
        report = session.get(RuleQualityReport, report_id)
        assert report is not None
        assert report.status == "SUCCESS"
        assert report.result == {"sentinel": "already-computed"}
        assert report.completed_at == completed_at


def test_worker_recovery_configuration_uses_late_acknowledgements(reset_recovery_state: Redis):
    del reset_recovery_state
    assert celery_app.conf.task_acks_late is True
    assert celery_app.conf.task_reject_on_worker_lost is True
    assert celery_app.conf.task_track_started is True
    assert celery_app.conf.worker_prefetch_multiplier == 1
    assert celery_app.conf.broker_transport_options["visibility_timeout"] == 3600
