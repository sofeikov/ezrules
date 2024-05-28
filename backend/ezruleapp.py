import difflib
import json
import logging
import os
import secrets

from flask import (Flask, Response, flash, jsonify, redirect, render_template,
                   request, url_for)
from flask_bootstrap import Bootstrap5
from flask_security import (Security, SQLAlchemySessionUserDatastore,
                            auth_required)
from flask_wtf import CSRFProtect

from backend.forms import OutcomeForm, RuleForm
from backend.utils import conditional_decorator
from core.outcomes import FixedOutcome
from core.rule import Rule, RuleConverter, RuleFactory
from core.rule_checkers import (OnlyAllowedOutcomesAreReturnedChecker,
                                RuleCheckingPipeline)
from core.rule_updater import (RDBRuleEngineConfigProducer, RuleManager,
                               RuleManagerFactory, RuleRevision)
from core.user_lists import StaticUserListManager
from models.backend_core import Role
from models.backend_core import Rule as RuleModel
from models.backend_core import User
from models.database import db_session, init_db

outcome_manager = FixedOutcome()
rule_checker = RuleCheckingPipeline(
    checkers=[OnlyAllowedOutcomesAreReturnedChecker(outcome_manager=outcome_manager)]
)


# init_db()

app = Flask(__name__)
app.logger.setLevel(logging.INFO)
app.secret_key = os.environ["APP_SECRET"]
app.config["SECURITY_PASSWORD_SALT"] = os.environ.get(
    "SECURITY_PASSWORD_SALT", "146585145368132386173505678016728509634"
)
app.config["SECURITY_SEND_REGISTER_EMAIL"] = False
app.config["SECURITY_REGISTERABLE"] = True
app.config["TESTING"] = os.getenv("TESTING", False) == "true"
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
app.config["EVALUATOR_ENDPOINT"] = os.getenv("EVALUATOR_ENDPOINT")
bootstrap = Bootstrap5(app)
csrf = CSRFProtect(app)
url_safe_token = secrets.token_urlsafe(16)
app.secret_key = url_safe_token
o_id = int(os.getenv("O_ID", "1"))
fsrm: RuleManager = RuleManagerFactory.get_rule_manager(
    "RDBRuleManager", **{"db": db_session, "o_id": o_id}
)

app.teardown_appcontext(lambda exc: db_session.close())
user_datastore = SQLAlchemySessionUserDatastore(db_session, User, Role)
app.security = Security(app, user_datastore)
rule_engine_config_producer = RDBRuleEngineConfigProducer(db=db_session, o_id=o_id)


@app.route("/rules", methods=["GET"])
@app.route("/", methods=["GET"])
@conditional_decorator(not app.config["TESTING"], auth_required())
def rules():
    rules = fsrm.load_all_rules()
    return render_template("rules.html", rules=rules, evaluator_endpoint=app.config["EVALUATOR_ENDPOINT"])


@app.route("/create_rule", methods=["GET", "POST"])
@conditional_decorator(not app.config["TESTING"], auth_required())
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
        # Make sure we can compile the rule
        rule = RuleFactory.from_json(rule_raw_config)
        new_rule = RuleModel(
            rid=rule.rid, logic=rule._source, description=rule.description
        )
        fsrm.save_rule(new_rule)
        app.logger.info("Saving new version of the rules")
        rule_engine_config_producer.save_config(fsrm)
        app.logger.info(rule)
        return redirect(url_for("show_rule", rule_id=new_rule.r_id))


@app.route("/rule/<int:rule_id>/timeline", methods=["GET"])
@conditional_decorator(not app.config["TESTING"], auth_required())
def timeline(rule_id):
    latest_version = fsrm.load_rule(rule_id)
    revision_list = fsrm.get_rule_revision_list(latest_version)
    rules = [
        fsrm.load_rule(rule_id, revision_number=r.revision_number)
        for r in revision_list
    ]
    # Add the current version
    rules = [RuleFactory.from_json(r.__dict__) for r in rules]
    revision_list.append(
        RuleRevision(revision_number=latest_version.version, created=None)
    )
    rules.append(RuleFactory.from_json(latest_version.__dict__))
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


@app.route("/rule/<int:rule_id>", methods=["GET", "POST"])
@app.route("/rule/<int:rule_id>/<revision_number>", methods=["GET"])
@conditional_decorator(not app.config["TESTING"], auth_required())
def show_rule(rule_id=None, revision_number=None):
    if revision_number is not None:
        revision_number = int(revision_number)
    form = RuleForm()
    if request.method == "GET":
        rule = fsrm.load_rule(rule_id, revision_number=revision_number)
        if rule is None:
            return Response("Rule not found", 404)
        compiled_rule = RuleFactory.from_json(rule.__dict__)
        rule_json = RuleConverter.to_json(compiled_rule)
        rule_json = rule.__dict__
        app.logger.info(rule_json)
        form.process(**rule_json)
        del form.rid
        revision_list = fsrm.get_rule_revision_list(rule)
        return render_template(
            "show_rule.html",
            rule=rule_json,
            form=form,
            revision_list=revision_list,
        )
    elif request.method == "POST":
        rule_status_check = form.validate(rule_checker=rule_checker)
        if not rule_status_check.rule_ok:
            flash("The rule changes have not been saved, because:")
            for r in rule_status_check.reasons:
                flash(r)
            return redirect(url_for("show_rule", rule_id=rule_id))
        app.logger.info(request.form)
        rule = fsrm.load_rule(rule_id)
        app.logger.info(f"Current rule state {rule}")
        rule.description = form.description.data
        rule.logic = form.logic.data
        fsrm.save_rule(rule)
        app.logger.info("Saving new version of the rules")
        rule_engine_config_producer.save_config(fsrm)
        app.logger.info(f"Changing {rule_id}")
        flash(f"Changes to {rule_id} were saved")
        return redirect(url_for("show_rule", rule_id=rule_id))


@app.route("/verify_rule", methods=["POST"])
@csrf.exempt
def verifyty_rule():
    source_ = None
    try:
        source_ = request.get_json()["rule_source"]
        rule = Rule(rid="", logic=source_)
    except:
        app.logger.info(f"Failed to compile logic: {source_}")
        return {}
    app.logger.info(f"About to return these params: {rule.get_rule_params()}")
    return jsonify(params=sorted(list(rule.get_rule_params()), key=str))


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


@app.route("/management/outcomes", methods=["GET", "POST"])
@conditional_decorator(not app.config["TESTING"], auth_required())
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


@app.route("/management/lists", methods=["GET", "POST"])
@conditional_decorator(not app.config["TESTING"], auth_required())
def user_lists():
    return render_template(
        "user_lists.html", user_lists=StaticUserListManager().get_all_entries()
    )


@app.route("/ping", methods=["GET"])
@csrf.exempt
def ping():
    return "OK"
