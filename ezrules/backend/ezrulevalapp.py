from flask import Flask, abort, jsonify, request
from pydantic import ValidationError

from ezrules.backend.data_utils import Event, eval_and_store
from ezrules.backend.rule_executors.executors import LocalRuleExecutorSQL
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
        event = Event(
            event_id=request_data["event_id"],
            event_timestamp=request_data["event_timestamp"],
            event_data=request_data["event_data"],
        )
    except ValidationError:
        abort(400, description="Bad Request: Could not validate the json structure")
    response = eval_and_store(lre, event)
    return jsonify(response)


@app.route("/ping", methods=["GET"])
def ping():
    return "OK"
