from datetime import UTC, datetime, timedelta
from typing import Any, cast

from celery import Celery

from ezrules.backend.alerts import detect_alerts_for_decision, sweep_alert_rules
from ezrules.backend.backtesting import (
    BACKTEST_QUEUE_CANCELLED,
    BACKTEST_QUEUE_DONE,
    BACKTEST_QUEUE_FAILED,
    BACKTEST_QUEUE_RUNNING,
    BacktestRecord,
    compute_backtest_metrics,
)
from ezrules.backend.observation_queue import drain_observation_queue
from ezrules.backend.rule_quality import (
    compute_rule_quality_metrics,
    get_active_rule_quality_pairs,
    normalize_rule_quality_pairs,
)
from ezrules.backend.shadow_evaluation_queue import drain_shadow_evaluation_queue
from ezrules.backend.utils import load_cast_configs
from ezrules.core.application_context import set_organization_id, set_user_list_manager
from ezrules.core.rule import Rule, RuleFactory
from ezrules.core.user_lists import PersistentUserListManager
from ezrules.models.backend_core import (
    EvaluationDecision,
    EventVersion,
    EventVersionLabel,
    Label,
    RuleBackTestingResult,
    RuleQualityReport,
)
from ezrules.models.backend_core import Rule as RuleModel
from ezrules.models.database import db_session
from ezrules.settings import app_settings

app = Celery("tasks", backend=f"db+{app_settings.DB_ENDPOINT}", broker=app_settings.CELERY_BROKER_URL)
app.conf.beat_schedule = {
    "drain-field-observation-queue": {
        "task": "ezrules.backend.tasks.drain_field_observation_queue",
        "schedule": timedelta(seconds=app_settings.OBSERVATION_QUEUE_DRAIN_INTERVAL_SECONDS),
    },
    "drain-shadow-evaluation-queue": {
        "task": "ezrules.backend.tasks.drain_shadow_evaluation_queue_task",
        "schedule": timedelta(seconds=app_settings.SHADOW_EVALUATION_QUEUE_DRAIN_INTERVAL_SECONDS),
    },
    "sweep-alert-rules": {
        "task": "ezrules.backend.tasks.sweep_alert_rules_task",
        "schedule": timedelta(seconds=app_settings.ALERT_SWEEP_INTERVAL_SECONDS),
    },
}


def _get_backtest_record(task_id: str | None) -> RuleBackTestingResult | None:
    if not task_id:
        return None
    return db_session.query(RuleBackTestingResult).filter(RuleBackTestingResult.task_id == task_id).first()


def _persist_backtest_state(
    task_id: str,
    *,
    status: str,
    result_metrics: dict[str, Any] | None = None,
    completed_at: datetime | None = None,
    skip_if_cancelled: bool = False,
) -> None:
    try:
        record = _get_backtest_record(task_id)
        if record is None:
            return
        if skip_if_cancelled and record.status == BACKTEST_QUEUE_CANCELLED:
            return

        record.status = status
        record.result_metrics = result_metrics
        record.completed_at = completed_at
        db_session.commit()
    except Exception:
        db_session.rollback()
        raise


def _load_backtest_snapshot(
    *,
    r_id: int,
    new_rule_logic: str,
    org_id: int,
    task_id: str | None,
) -> tuple[RuleModel | None, str | None, str, dict[str, Any] | None]:
    record = _get_backtest_record(task_id)
    if record is None:
        rule_obj = db_session.query(RuleModel).filter(RuleModel.r_id == r_id, RuleModel.o_id == org_id).first()
        if rule_obj is None:
            return None, None, new_rule_logic, None
        return rule_obj, cast(str | None, rule_obj.logic), new_rule_logic, None

    existing_payload = record.result_metrics if isinstance(record.result_metrics, dict) else None
    if existing_payload is not None and record.status in {
        BACKTEST_QUEUE_DONE,
        BACKTEST_QUEUE_FAILED,
        BACKTEST_QUEUE_CANCELLED,
    }:
        return (
            cast(RuleModel | None, record.rule),
            cast(str | None, record.stored_logic),
            cast(str, record.proposed_logic or new_rule_logic),
            existing_payload,
        )

    if record.status == BACKTEST_QUEUE_CANCELLED:
        return (
            cast(RuleModel | None, record.rule),
            cast(str | None, record.stored_logic),
            cast(str, record.proposed_logic or new_rule_logic),
            {"error": "Backtest was cancelled before execution began"},
        )

    rule_obj = cast(RuleModel | None, record.rule)
    if rule_obj is None:
        return None, None, cast(str, record.proposed_logic or new_rule_logic), None

    _persist_backtest_state(
        str(task_id),
        status=BACKTEST_QUEUE_RUNNING,
        result_metrics=None,
        completed_at=None,
    )
    return (
        rule_obj,
        cast(str | None, record.stored_logic or rule_obj.logic),
        cast(str, record.proposed_logic or new_rule_logic),
        None,
    )


def execute_backtest_rule_change(
    r_id: int,
    new_rule_logic: str,
    org_id: int,
    *,
    task_id: str | None = None,
) -> dict[str, Any]:
    try:
        rule_obj, stored_logic, proposed_logic, early_payload = _load_backtest_snapshot(
            r_id=r_id,
            new_rule_logic=new_rule_logic,
            org_id=org_id,
            task_id=task_id,
        )
        if early_payload is not None:
            return early_payload

        if rule_obj is None:
            payload = {"error": f"Rule with id {r_id} not found"}
            if task_id is not None:
                _persist_backtest_state(
                    task_id,
                    status=BACKTEST_QUEUE_FAILED,
                    result_metrics=payload,
                    completed_at=datetime.now(UTC),
                    skip_if_cancelled=True,
                )
            return payload

        # Set up application context for background task
        list_provider = PersistentUserListManager(db_session=db_session, o_id=org_id)
        set_organization_id(org_id)
        set_user_list_manager(list_provider)

        try:
            stored_rule = RuleFactory.from_json(
                {
                    **rule_obj.__dict__,
                    "logic": stored_logic or rule_obj.logic,
                },
                list_values_provider=list_provider,
            )
        except Exception as e:
            payload = {"error": f"Failed to compile stored rule: {e!s}"}
            if task_id is not None:
                _persist_backtest_state(
                    task_id,
                    status=BACKTEST_QUEUE_FAILED,
                    result_metrics=payload,
                    completed_at=datetime.now(UTC),
                    skip_if_cancelled=True,
                )
            return payload

        try:
            proposed_rule = Rule(rid="", logic=proposed_logic, list_values_provider=list_provider)
        except Exception as e:
            payload = {"error": f"Failed to compile proposed rule logic: {e!s}"}
            if task_id is not None:
                _persist_backtest_state(
                    task_id,
                    status=BACKTEST_QUEUE_FAILED,
                    result_metrics=payload,
                    completed_at=datetime.now(UTC),
                    skip_if_cancelled=True,
                )
            return payload

        one_month_ago = datetime.now(UTC) - timedelta(days=30)

        try:
            query = (
                db_session.query(EventVersion.event_data, Label.label)
                .join(EvaluationDecision, EvaluationDecision.ev_id == EventVersion.ev_id)
                .outerjoin(
                    EventVersionLabel,
                    (EventVersionLabel.ev_id == EventVersion.ev_id) & (EventVersionLabel.o_id == org_id),
                )
                .outerjoin(Label, (Label.el_id == EventVersionLabel.el_id) & (Label.o_id == org_id))
                .filter(
                    EvaluationDecision.evaluated_at >= one_month_ago,
                    EvaluationDecision.o_id == org_id,
                    EvaluationDecision.served.is_(True),
                    EvaluationDecision.decision_type == "served",
                )
            )
        except Exception as e:
            payload = {"error": f"Failed to query test records: {e!s}"}
            if task_id is not None:
                _persist_backtest_state(
                    task_id,
                    status=BACKTEST_QUEUE_FAILED,
                    result_metrics=payload,
                    completed_at=datetime.now(UTC),
                    skip_if_cancelled=True,
                )
            return payload

        configs = load_cast_configs(db_session, org_id)

        payload = compute_backtest_metrics(
            stored_rule=stored_rule,
            proposed_rule=proposed_rule,
            test_records=(
                BacktestRecord(event_data=dict(row.event_data or {}), label_name=str(row.label) if row.label else None)
                for row in query.yield_per(5000)
            ),
            configs=configs,
        )
    except Exception as e:
        db_session.rollback()
        payload = {"error": f"Backtest task failed: {e!s}"}

    if task_id is not None:
        _persist_backtest_state(
            task_id,
            status=BACKTEST_QUEUE_FAILED if "error" in payload else BACKTEST_QUEUE_DONE,
            result_metrics=payload,
            completed_at=datetime.now(UTC),
            skip_if_cancelled=True,
        )

    return payload


@app.task(bind=True)
def backtest_rule_change(self, r_id: int, new_rule_logic: str, org_id: int):
    task_id = str(self.request.id) if getattr(self.request, "id", None) else None
    return execute_backtest_rule_change(
        r_id,
        new_rule_logic,
        org_id,
        task_id=task_id,
    )


@app.task
def generate_rule_quality_report(report_id: int) -> dict[str, str]:
    report = db_session.get(RuleQualityReport, report_id)
    if report is None:
        return {"error": f"Rule quality report {report_id} not found"}

    try:
        report.status = "RUNNING"
        report.started_at = datetime.now(UTC)
        report.error = None
        db_session.commit()

        snapshot_pairs = []
        if report.pair_set:
            snapshot_pairs = [
                (str(item.get("outcome", "")), str(item.get("label", "")))
                for item in report.pair_set
                if isinstance(item, dict)
            ]
        curated_pairs = normalize_rule_quality_pairs(snapshot_pairs)
        if not curated_pairs:
            curated_pairs = get_active_rule_quality_pairs(db_session, o_id=report.o_id)

        payload = compute_rule_quality_metrics(
            db_session,
            min_support=report.min_support,
            lookback_days=report.lookback_days,
            freeze_at=report.freeze_at,
            max_decision_id=report.max_decision_id,
            o_id=report.o_id,
            curated_pairs=curated_pairs,
        )
        payload["freeze_at"] = payload["freeze_at"].isoformat()

        report.result = payload
        report.status = "SUCCESS"
        report.completed_at = datetime.now(UTC)
        report.error = None
        db_session.commit()
        return {"status": "SUCCESS"}
    except Exception as e:
        db_session.rollback()
        report = db_session.get(RuleQualityReport, report_id)
        if report is not None:
            report.status = "FAILURE"
            report.error = str(e)
            report.completed_at = datetime.now(UTC)
            db_session.commit()
        return {"error": f"Rule quality report {report_id} failed: {e!s}"}


@app.task(name="ezrules.backend.tasks.drain_field_observation_queue")
def drain_field_observation_queue() -> dict[str, int]:
    return drain_observation_queue()


@app.task(name="ezrules.backend.tasks.drain_shadow_evaluation_queue_task")
def drain_shadow_evaluation_queue_task() -> dict[str, int]:
    return drain_shadow_evaluation_queue()


@app.task(name="ezrules.backend.tasks.detect_alerts_for_decision_task")
def detect_alerts_for_decision_task(o_id: int, evaluation_decision_id: int) -> dict[str, int]:
    incident_ids = detect_alerts_for_decision(db_session, o_id=o_id, evaluation_decision_id=evaluation_decision_id)
    return {"incidents": len(incident_ids)}


@app.task(name="ezrules.backend.tasks.sweep_alert_rules_task")
def sweep_alert_rules_task() -> dict[str, int]:
    return sweep_alert_rules(db_session)
