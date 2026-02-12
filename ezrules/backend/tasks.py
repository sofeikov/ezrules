from collections import Counter
from datetime import UTC, datetime, timedelta

from celery import Celery

from ezrules.core.application_context import set_organization_id, set_user_list_manager
from ezrules.core.rule import Rule, RuleFactory
from ezrules.core.user_lists import PersistentUserListManager
from ezrules.models.backend_core import Rule as RuleModel
from ezrules.models.backend_core import TestingRecordLog
from ezrules.models.database import db_session
from ezrules.settings import app_settings

app = Celery("tasks", backend=f"db+{app_settings.DB_ENDPOINT}", broker=app_settings.CELERY_BROKER_URL)


@app.task
def backtest_rule_change(r_id: int, new_rule_logic: str):
    rule_obj = db_session.get(RuleModel, r_id)
    if rule_obj is None:
        return {"error": f"Rule with id {r_id} not found"}

    # Set up application context for background task
    list_provider = PersistentUserListManager(db_session=db_session, o_id=app_settings.ORG_ID)
    set_organization_id(app_settings.ORG_ID)
    set_user_list_manager(list_provider)

    try:
        stored_rule = RuleFactory.from_json(rule_obj.__dict__)
    except Exception as e:
        return {"error": f"Failed to compile stored rule: {e!s}"}

    try:
        proposed_rule = Rule(rid="", logic=new_rule_logic)
    except Exception as e:
        return {"error": f"Failed to compile proposed rule logic: {e!s}"}

    one_month_ago = datetime.now(UTC) - timedelta(days=30)

    try:
        query = db_session.query(TestingRecordLog).filter(
            TestingRecordLog.created_at >= one_month_ago,
            TestingRecordLog.o_id == app_settings.ORG_ID,
        )
    except Exception as e:
        return {"error": f"Failed to query test records: {e!s}"}

    stored_counter: Counter[str] = Counter()
    proposed_counter: Counter[str] = Counter()
    total_records = 0

    for record in query.yield_per(5000):
        total_records += 1
        stored_outcome = stored_rule(record.event)
        proposed_outcome = proposed_rule(record.event)
        if stored_outcome is not None:
            stored_counter[str(stored_outcome)] += 1
        if proposed_outcome is not None:
            proposed_counter[str(proposed_outcome)] += 1

    stored_result = dict(stored_counter)
    proposed_result = dict(proposed_counter)

    if total_records > 0:
        stored_result_rate = {outcome: 100 * ct / total_records for outcome, ct in stored_result.items()}
        proposed_result_rate = {outcome: 100 * ct / total_records for outcome, ct in proposed_result.items()}
    else:
        stored_result_rate = {}
        proposed_result_rate = {}

    return {
        "stored_result": stored_result,
        "proposed_result": proposed_result,
        "stored_result_rate": stored_result_rate,
        "proposed_result_rate": proposed_result_rate,
        "total_records": total_records,
    }
