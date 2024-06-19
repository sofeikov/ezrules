from flask import Flask, request

from ezrules.backend.rule_executors.executors import LocalRuleExecutorSQL
from ezrules.models.database import db_session
from ezrules.models.backend_core import TestingLog
from ezrules.settings import app_settings

app = Flask(__name__)
# TODO calling this needs to be parametrised, e.g. for a remote service
o_id = app_settings.ORG_ID
lre = LocalRuleExecutorSQL(db=db_session, o_id=o_id)


@app.route("/evaluate", methods=["POST"])
def evaluate():
    request_data = request.get_json()
    db_session = lre.db
    tl = TestingLog(o_id=lre.o_id, event=request_data)
    db_session.add(tl)
    db_session.commit()
    response = lre.evaluate_rules(request_data)
    return response


@app.route("/ping", methods=["GET"])
def ping():
    return f"OK"
