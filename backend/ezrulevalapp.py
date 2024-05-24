from flask import Flask, request
from backend.rule_executors.executors import LocalRuleExecutorSQL
from models.database import db_session
import os

app = Flask(__name__)
# TODO calling this needs to be parametrised, e.g. for a remote service
o_id = int(os.getenv("O_ID", "1"))
lre = LocalRuleExecutorSQL(db=db_session, o_id=o_id)


@app.route("/evaluate", methods=["POST"])
def evaluate():
    request_data = request.get_json()
    response = lre.evaluate_rules(request_data)
    return response


@app.route("/ping", methods=["GET"])
def ping():
    return f"OK"