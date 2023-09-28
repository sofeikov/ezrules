from flask import Flask, request
from backend.rule_executors.executors import LambdaRuleExecutor

app = Flask(__name__)
# TODO calling this needs to be parametrised, e.g. for a remote service
# TODO this needs to be parametrised

lre = LambdaRuleExecutor("ezrule-executor-dev")


@app.route("/evaluate", methods=["POST"])
def evaluate():
    request_data = request.get_json()
    print(request_data)
    response = lre.evaluate_rules(request_data)
    return response


@app.route("/", methods=["GET"])
def root():
    return "EZRule rule evaluator app"


@app.route("/ping", methods=["GET"])
def ping():
    return "OK"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=9999, debug=True)
