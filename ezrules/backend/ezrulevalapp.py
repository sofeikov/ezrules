from flask import Flask, request, abort, jsonify
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
        event = Event(**request_data)
    except ValidationError as e:
        abort(400, description="Bad Request: Could not validate the json structure")
    response = eval_and_store(lre, event)
    return jsonify(response)


@app.route("/ping", methods=["GET"])
def ping():
    return f"OK"
