from flask import Flask, request
from backend.rule_executors.executors import LocalRuleExecutorSQL
from models.database import db_session
from models.backend_core import RunResult
import os

app = Flask(__name__)
# TODO calling this needs to be parametrised, e.g. for a remote service
o_id = int(os.getenv("O_ID", "1"))
lre = LocalRuleExecutorSQL(db=db_session, o_id=o_id)


@app.route("/evaluate", methods=["POST"])
def evaluate():
    request_data = request.get_json()
    response = lre.evaluate_rules(request_data)

    rr = RunResult(
        rec_id=lre.self_id,
        rec_version=lre._current_rule_version,
        event=request_data,
        result=response,
    )
    db_session.add(rr)
    db_session.commit()

    return response


@app.route("/ping", methods=["GET"])
def ping():
    return f"OK"
