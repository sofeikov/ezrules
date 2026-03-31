from datetime import UTC, datetime, timedelta
from typing import Any

from celery import Celery

from ezrules.backend.backtesting import (
    BACKTEST_QUEUE_CANCELLED,
    BACKTEST_QUEUE_DONE,
    BACKTEST_QUEUE_FAILED,
    BACKTEST_QUEUE_RUNNING,
    compute_backtest_metrics,
)
from ezrules.backend.rule_quality import (
    compute_rule_quality_metrics,
    get_active_rule_quality_pairs,
    normalize_rule_quality_pairs,
)
from ezrules.backend.utils import load_cast_configs
from ezrules.core.application_context import set_organization_id, set_user_list_manager
from ezrules.core.rule import Rule, RuleFactory
from ezrules.core.user_lists import PersistentUserListManager
from ezrules.models.backend_core import Label, RuleBackTestingResult, RuleQualityReport, TestingRecordLog
from ezrules.models.backend_core import Rule as RuleModel
from ezrules.models.database import db_session
from ezrules.settings import app_settings

app = Celery("tasks", backend=f"db+{app_settings.DB_ENDPOINT}", broker=app_settings.CELERY_BROKER_URL)


def _persist_backtest_state(
    backtest_id: int,
    *,
    status: str,
    result_metrics: dict[str, Any] | None = None,
    completed_at: datetime | None = None,
    task_id: str | None = None,
    skip_if_cancelled: bool = False,
) -> None:
    try:
        record = db_session.get(RuleBackTestingResult, backtest_id)
        if record is None:
            return
        if skip_if_cancelled and record.status == BACKTEST_QUEUE_CANCELLED:
            return

        record.status = status
        record.result_metrics = result_metrics
        record.completed_at = completed_at
        if task_id:
            record.task_id = task_id
        db_session.commit()
    except Exception:
        db_session.rollback()
        raise


def _load_backtest_snapshot(
    *,
    r_id: int,
    new_rule_logic: str,
    org_id: int,
    backtest_id: int | None,
    task_id: str | None,
) -> tuple[RuleModel | None, str | None, str, dict[str, Any] | None]:
    if backtest_id is None:
        rule_obj = db_session.query(RuleModel).filter(RuleModel.r_id == r_id, RuleModel.o_id == org_id).first()
        if rule_obj is None:
            return None, None, new_rule_logic, None
        return rule_obj, rule_obj.logic, new_rule_logic, None

    record = db_session.get(RuleBackTestingResult, backtest_id)
    if record is None:
        return None, None, new_rule_logic, {"error": f"Backtest record {backtest_id} not found"}
    if record.status == BACKTEST_QUEUE_CANCELLED:
        return (
            record.rule,
            record.stored_logic,
            record.proposed_logic or new_rule_logic,
            {"error": "Backtest was cancelled before execution began"},
        )

    rule_obj = record.rule
    if rule_obj is None:
        return None, None, record.proposed_logic or new_rule_logic, None

    _persist_backtest_state(
        backtest_id,
        status=BACKTEST_QUEUE_RUNNING,
        result_metrics=None,
        completed_at=None,
        task_id=str(task_id) if task_id else None,
    )
    return rule_obj, record.stored_logic or rule_obj.logic, record.proposed_logic or new_rule_logic, None


@app.task(bind=True)
def backtest_rule_change(self, r_id: int, new_rule_logic: str, org_id: int, backtest_id: int | None = None):
    try:
        rule_obj, stored_logic, proposed_logic, early_payload = _load_backtest_snapshot(
            r_id=r_id,
            new_rule_logic=new_rule_logic,
            org_id=org_id,
            backtest_id=backtest_id,
            task_id=str(self.request.id) if getattr(self.request, "id", None) else None,
        )
        if early_payload is not None:
            return early_payload

        if rule_obj is None:
            payload = {"error": f"Rule with id {r_id} not found"}
            if backtest_id is not None:
                _persist_backtest_state(
                    backtest_id,
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
            if backtest_id is not None:
                _persist_backtest_state(
                    backtest_id,
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
            if backtest_id is not None:
                _persist_backtest_state(
                    backtest_id,
                    status=BACKTEST_QUEUE_FAILED,
                    result_metrics=payload,
                    completed_at=datetime.now(UTC),
                    skip_if_cancelled=True,
                )
            return payload

        one_month_ago = datetime.now(UTC) - timedelta(days=30)

        try:
            query = db_session.query(TestingRecordLog).filter(
                TestingRecordLog.created_at >= one_month_ago,
                TestingRecordLog.o_id == org_id,
            )
        except Exception as e:
            payload = {"error": f"Failed to query test records: {e!s}"}
            if backtest_id is not None:
                _persist_backtest_state(
                    backtest_id,
                    status=BACKTEST_QUEUE_FAILED,
                    result_metrics=payload,
                    completed_at=datetime.now(UTC),
                    skip_if_cancelled=True,
                )
            return payload

        label_lookup = {
            int(label_id): str(label_name)
            for label_id, label_name in db_session.query(Label.el_id, Label.label).filter(Label.o_id == org_id)
        }
        configs = load_cast_configs(db_session, org_id)

        payload = compute_backtest_metrics(
            stored_rule=stored_rule,
            proposed_rule=proposed_rule,
            test_records=query.yield_per(5000),
            label_lookup=label_lookup,
            configs=configs,
        )
    except Exception as e:
        db_session.rollback()
        payload = {"error": f"Backtest task failed: {e!s}"}

    if backtest_id is not None:
        _persist_backtest_state(
            backtest_id,
            status=BACKTEST_QUEUE_FAILED if "error" in payload else BACKTEST_QUEUE_DONE,
            result_metrics=payload,
            completed_at=datetime.now(UTC),
            task_id=str(self.request.id) if getattr(self.request, "id", None) else None,
            skip_if_cancelled=True,
        )

    return payload


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
            max_tl_id=report.max_tl_id,
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
