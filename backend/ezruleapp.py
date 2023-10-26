import difflib
import secrets
import os
import json
from flask import Flask, render_template, Response, redirect, url_for, flash
from flask import request
from flask_bootstrap import Bootstrap5
from flask_wtf import CSRFProtect
from forms import RuleForm, OutcomeForm

from core.rule import RuleFactory, RuleConverter, Rule
from core.outcomes import FixedOutcome
from core.rule_checkers import (
    RuleCheckingPipeline,
    OnlyAllowedOutcomesAreReturnedChecker,
)
from core.rule_updater import (
    RuleManagerFactory,
    RuleDoesNotExistInTheStorage,
    RuleEngineConfigProducer,
)
from core.rule_locker import DynamoDBStorageLocker

rule_locker = DynamoDBStorageLocker(
    table_name=os.environ["DYNAMODB_RULE_LOCKER_TABLE_NAME"]
)
outcome_manager = FixedOutcome()
rule_checker = RuleCheckingPipeline(
    checkers=[OnlyAllowedOutcomesAreReturnedChecker(outcome_manager=outcome_manager)]
)
app = Flask(__name__)
app.secret_key = os.environ["APP_SECRET"]
bootstrap = Bootstrap5(app)
csrf = CSRFProtect(app)
url_safe_token = secrets.token_urlsafe(16)
app.secret_key = url_safe_token
EZRULES_BUCKET = os.environ["EZRULES_BUCKET"]
EZRULES_BUCKET_PATH = f"s3://{EZRULES_BUCKET}"
DYNAMODB_TABLE_NAME = os.environ["DYNAMODB_RULE_MANAGER_TABLE_NAME"]
app.logger.info(f"DynamoDB table is {DYNAMODB_TABLE_NAME}")
fsrm = RuleManagerFactory.get_rule_manager(
    "DynamoDBRuleManager",
    **{"table_name": DYNAMODB_TABLE_NAME},
)


@app.route("/rules", methods=["GET"])
@app.route("/", methods=["GET"])
def rules():
    rules = fsrm.load_all_rules()
    return render_template("rules.html", rules=rules)


@app.route("/create_rule", methods=["GET", "POST"])
def create_rule():
    form = RuleForm()
    if request.method == "GET":
        return render_template("create_rule.html", form=form)
    elif request.method == "POST":
        rule_status_check = form.validate(rule_checker=rule_checker)
        if not rule_status_check.rule_ok:
            flash("The rule changes have not been saved, because:")
            for r in rule_status_check.reasons:
                flash(r)
            return render_template("create_rule.html", form=form)
        rule_raw_config = form.data
        app.logger.info(rule_raw_config)
        rule = RuleFactory.from_json(rule_raw_config)
        fsrm.save_rule(rule)
        app.logger.info("Saving new version of the rules")
        RuleEngineConfigProducer.to_yaml(
            os.path.join(EZRULES_BUCKET_PATH, "rule-config.yaml"), fsrm
        )
        app.logger.info(rule)
        return redirect(url_for("show_rule", rule_id=rule.rid))


@app.route("/get_all_rules", methods=["GET"])
def get_all_rules():
    all_rules = [RuleConverter.to_json(r) for r in fsrm.load_all_rules()]
    return all_rules


@app.route("/rule/<rule_id>/timeline", methods=["GET"])
def timeline(rule_id):
    revision_list = fsrm.get_rule_revision_list(rule_id)
    rules = [
        fsrm.load_rule(rule_id, revision_number=r.revision_number)
        for r in revision_list
    ]
    logics = [r._source for r in rules]
    diff_timeline = []
    for ct, (l1, l2) in enumerate(zip(logics[:-1], logics[1:])):
        diff = difflib.HtmlDiff().make_file(
            fromlines=l1.split("\n"),
            tolines=l2.split("\n"),
            fromdesc=f"Revision {revision_list[ct].revision_number}",
            todesc=f"Revision {revision_list[ct+1].revision_number}",
        )
        diff_timeline.append(diff)

    return render_template("timeline.html", timeline=diff_timeline, rule=rule_id)


@app.route("/rule/<rule_id>", methods=["GET", "POST"])
@app.route("/rule/<rule_id>/<revision_number>", methods=["GET"])
def show_rule(rule_id=None, revision_number=None):
    form = RuleForm()
    if request.method == "GET":
        try:
            if revision_number is not None:
                revision_number = int(revision_number)
            rule = fsrm.load_rule(rule_id, revision_number=revision_number)
            rule_json = RuleConverter.to_json(rule)
            app.logger.info(rule_json)
            form.process(**rule_json)
            del form.rid
            revision_list = fsrm.get_rule_revision_list(rule)
            rule_lock = rule_locker.is_record_locked(rule)
            return render_template(
                "show_rule.html",
                rule=rule_json,
                form=form,
                revision_list=revision_list,
                rule_lock=rule_lock,
            )
        except RuleDoesNotExistInTheStorage:
            return Response("Rule not found", 404)
    elif request.method == "POST":
        rule_status_check = form.validate(rule_checker=rule_checker)
        if not rule_status_check.rule_ok:
            flash("The rule changes have not been saved, because:")
            for r in rule_status_check.reasons:
                flash(r)
            return redirect(url_for("show_rule", rule_id=rule_id))
        app.logger.info(request.form)
        rule = fsrm.load_rule(rule_id)
        # TODO reject the change is the rule is locked
        app.logger.info(f"Current rule state {rule}")
        rule.description = form.description.data
        rule.logic = form.logic.data
        rule.tags = form.tags.data
        rule.params = form.params.data

        fsrm.save_rule(rule)
        app.logger.info("Saving new version of the rules")
        RuleEngineConfigProducer.to_yaml(
            os.path.join(EZRULES_BUCKET_PATH, "rule-config.yaml"), fsrm
        )
        app.logger.info(f"Changing {rule_id}")
        flash(f"Changes to {rule_id} were saved")
        return redirect(url_for("show_rule", rule_id=rule_id))


@app.route("/verify_rule", methods=["POST"])
@csrf.exempt
def verify_rule():
    source_ = None
    try:
        source_ = request.get_json()["rule_source"]
        rule = Rule(rid="", logic=source_)
    except:
        app.logger.debug(f"Failed to compile logic: {source_}")
        return {}
    return {"params": sorted(list(rule.get_rule_params()), key=str)}


@app.route("/test_rule", methods=["POST"])
@csrf.exempt
def test_rule():
    test_json = request.get_json()
    rule_source = test_json["rule_source"]
    print(rule_source)
    try:
        test_object = json.loads(test_json["test_json"])
    except json.decoder.JSONDecodeError:
        return {
            "status": "error",
            "reason": "Example is malformed",
            "rule_outcome": None,
        }
    try:
        rule = Rule(rid="", logic=rule_source)
    except SyntaxError:
        return {
            "status": "error",
            "reason": "Rule source is invalid",
            "rule_outcome": None,
        }
    rule_outcome = rule(test_object)
    return {"rule_outcome": rule_outcome, "status": "ok", "reason": "ok"}


@app.route("/lock_rule/<rule_id>", methods=["POST"])
@csrf.exempt
def lock_rule(rule_id):
    rule = fsrm.load_rule(rule_id)
    success, result = rule_locker.lock_storage(rule)
    return {"success": success, **result._asdict()}


@app.route("/unlock/<rule_id>", methods=["POST"])
@csrf.exempt
def unlock_rule(rule_id):
    rule = fsrm.load_rule(rule_id)
    rule_locker.release_storage(rule)
    return {}


@app.route("/management/outcomes", methods=["GET", "POST"])
def verified_outcomes():
    form = OutcomeForm()
    if request.method == "GET":
        return render_template(
            "outcomes.html", form=form, outcomes=outcome_manager.get_allowed_outcomes()
        )
    else:
        if form.validate():
            outcome_manager.add_outcome(form.outcome.data)
            return redirect(url_for("verified_outcomes"))


@app.route("/ping", methods=["GET"])
@csrf.exempt
def ping():
    return "OK"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8888, debug=True)
