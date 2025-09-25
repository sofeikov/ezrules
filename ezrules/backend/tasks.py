from collections import Counter
from datetime import datetime, timedelta

from celery import Celery

from ezrules.core.rule import Rule, RuleFactory
from ezrules.models.backend_core import Rule as RuleModel
from ezrules.models.backend_core import TestingRecordLog
from ezrules.models.database import db_session
from ezrules.settings import app_settings

app = Celery("tasks", backend=f"db+{app_settings.DB_ENDPOINT}", broker="redis://localhost:6379")


def count_rule_outcomes(rule: Rule, test_records: list[TestingRecordLog]) -> dict[str, int]:
    stored_result = dict(Counter([rule(r.event) for r in test_records]))
    if None in stored_result:
        del stored_result[None]
    return stored_result


@app.task
def backtest_rule_change(r_id: int, new_rule_logic: str):
    rule_obj = db_session.get(RuleModel, r_id)
    # Set up application context for background task
    from ezrules.core.application_context import set_organization_id, set_user_list_manager
    from ezrules.core.user_lists import PersistentUserListManager

    list_provider = PersistentUserListManager(db_session=db_session, o_id=app_settings.ORG_ID)
    set_organization_id(app_settings.ORG_ID)
    set_user_list_manager(list_provider)

    stored_rule = RuleFactory.from_json(rule_obj.__dict__)
    proposed_rule = Rule(rid="", logic=new_rule_logic)

    one_month_ago = datetime.utcnow() - timedelta(days=30)
    query = db_session.query(TestingRecordLog).filter(
        TestingRecordLog.created_at >= one_month_ago,
        TestingRecordLog.o_id == app_settings.ORG_ID,
    )
    records = query.all()

    stored_result = count_rule_outcomes(stored_rule, records)
    proposed_result = count_rule_outcomes(proposed_rule, records)

    stored_result_rate = {outcome: 100 * ct / len(records) for outcome, ct in stored_result.items()}
    proposed_result_rate = {outcome: 100 * ct / len(records) for outcome, ct in proposed_result.items()}
    full_ret = {
        "stored_result": stored_result,
        "proposed_result": proposed_result,
        "stored_result_rate": stored_result_rate,
        "proposed_result_rate": proposed_result_rate,
    }

    return full_ret
