from flask import Flask, request, abort, jsonify
from pydantic import ValidationError

from ezrules.backend.data_utils import Event
from ezrules.backend.rule_executors.executors import LocalRuleExecutorSQL
from ezrules.models.backend_core import TestingRecordLog, TestingResultsLog
from ezrules.models.database import db_session
from ezrules.settings import app_settings

app = Flask(__name__)
# TODO calling this needs to be parametrised, e.g. for a remote service
o_id = app_settings.ORG_ID
lre = LocalRuleExecutorSQL(db=db_session, o_id=o_id)


@app.route("/evaluate", methods=["POST"])
def evaluate():
    request_data = request.get_json()
    try:
        event = Event(**request_data)
    except ValidationError as e:
        abort(400, description="Bad Request: Could not validate the json structure")
    db_session = lre.db
    tl = TestingRecordLog(
        o_id=lre.o_id,
        event=event.event_data,
        event_timestamp=event.event_timestamp,
        event_id=event.event_id,
    )
    db_session.add(tl)
    db_session.commit()
    response = lre.evaluate_rules(event.event_data)
    for r_id, result in response["rule_results"].items():
        trl = TestingResultsLog(tl_id=tl.tl_id, r_id=r_id, rule_result=result)
        db_session.add(trl)
    db_session.commit()
    return jsonify(response)


@app.route("/ping", methods=["GET"])
def ping():
    return f"OK"
