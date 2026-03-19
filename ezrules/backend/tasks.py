from datetime import UTC, datetime, timedelta

from celery import Celery

from ezrules.backend.backtesting import compute_backtest_metrics
from ezrules.backend.rule_quality import (
    compute_rule_quality_metrics,
    get_active_rule_quality_pairs,
    normalize_rule_quality_pairs,
)
from ezrules.core.application_context import set_organization_id, set_user_list_manager
from ezrules.core.rule import Rule, RuleFactory
from ezrules.core.user_lists import PersistentUserListManager
from ezrules.models.backend_core import Label, RuleQualityReport, TestingRecordLog
from ezrules.models.backend_core import Rule as RuleModel
from ezrules.models.database import db_session
from ezrules.settings import app_settings

app = Celery("tasks", backend=f"db+{app_settings.DB_ENDPOINT}", broker=app_settings.CELERY_BROKER_URL)


@app.task
def backtest_rule_change(r_id: int, new_rule_logic: str, org_id: int):
    rule_obj = db_session.query(RuleModel).filter(RuleModel.r_id == r_id, RuleModel.o_id == org_id).first()
    if rule_obj is None:
        return {"error": f"Rule with id {r_id} not found"}

    # Set up application context for background task
    list_provider = PersistentUserListManager(db_session=db_session, o_id=org_id)
    set_organization_id(org_id)
    set_user_list_manager(list_provider)

    try:
        stored_rule = RuleFactory.from_json(rule_obj.__dict__)
    except Exception as e:
        return {"error": f"Failed to compile stored rule: {e!s}"}

    try:
        proposed_rule = Rule(rid="", logic=new_rule_logic, list_values_provider=list_provider)
    except Exception as e:
        return {"error": f"Failed to compile proposed rule logic: {e!s}"}

    one_month_ago = datetime.now(UTC) - timedelta(days=30)

    try:
        query = db_session.query(TestingRecordLog).filter(
            TestingRecordLog.created_at >= one_month_ago,
            TestingRecordLog.o_id == org_id,
        )
    except Exception as e:
        return {"error": f"Failed to query test records: {e!s}"}

    label_lookup = {
        int(label_id): str(label_name)
        for label_id, label_name in db_session.query(Label.el_id, Label.label).filter(Label.o_id == org_id)
    }

    return compute_backtest_metrics(
        stored_rule=stored_rule,
        proposed_rule=proposed_rule,
        test_records=query.yield_per(5000),
        label_lookup=label_lookup,
    )


@app.task
def generate_rule_quality_report(report_id: int) -> dict[str, str]:
    report = db_session.get(RuleQualityReport, report_id)
    if report is None:
        return {"error": f"Rule quality report {report_id} not found"}

    try:
        report.status = "RUNNING"
        report.started_at = datetime.utcnow()
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
        report.completed_at = datetime.utcnow()
        report.error = None
        db_session.commit()
        return {"status": "SUCCESS"}
    except Exception as e:
        db_session.rollback()
        report = db_session.get(RuleQualityReport, report_id)
        if report is not None:
            report.status = "FAILURE"
            report.error = str(e)
            report.completed_at = datetime.utcnow()
            db_session.commit()
        return {"error": f"Rule quality report {report_id} failed: {e!s}"}
