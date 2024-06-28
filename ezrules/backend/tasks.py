from collections import Counter
from datetime import datetime, timedelta

from celery import Celery

from ezrules.core.rule import Rule, RuleFactory
from ezrules.models.backend_core import Rule as RuleModel
from ezrules.models.backend_core import TestingRecordLog
from ezrules.models.database import db_session
from ezrules.settings import app_settings

app = Celery(
    "tasks", backend=f"db+{app_settings.DB_ENDPOINT}", broker="redis://localhost:6379"
)


@app.task
def backtest_rule_change(r_id: int, new_rule_logic: str):
    rule_obj = db_session.get(RuleModel, r_id)
    stored_rule = RuleFactory.from_json(rule_obj.__dict__)
    proposed_rule = Rule(rid="", logic=new_rule_logic)

    one_month_ago = datetime.utcnow() - timedelta(days=30)
    query = db_session.query(TestingRecordLog).filter(
        TestingRecordLog.created_at >= one_month_ago,
        TestingRecordLog.o_id == app_settings.ORG_ID,
    )
    records = query.all()

    stored_result = dict(Counter([stored_rule(r.event) for r in records]))
    if None in stored_result:
        del stored_result[None]
    proposed_result = dict(Counter([proposed_rule(r.event) for r in records]))
    if None in proposed_result:
        del proposed_result[None]    

    stored_result_rate = {
        outcome: 100 * ct / len(records) for outcome, ct in stored_result.items()
    }
    proposed_result_rate = {
        outcome: 100 * ct / len(records) for outcome, ct in proposed_result.items()
    }
    full_ret = {
        "stored_result": stored_result,
        "proposed_result": proposed_result,
        "stored_result_rate": stored_result_rate,
        "proposed_result_rate": proposed_result_rate,
    }

    return full_ret


if __name__ == "__main__":
    res = backtest_rule_change.apply_async(args=[1, 'return "HOLD"'])
    print()
