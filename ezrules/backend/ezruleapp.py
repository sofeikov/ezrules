import difflib
import json
import logging
import os
import secrets
from json.decoder import JSONDecodeError
from typing import cast

import pandas as pd
import sqlalchemy
from celery.result import AsyncResult
from flask import (
    Flask,
    Response,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_bootstrap import Bootstrap5
from flask_security import Security, SQLAlchemySessionUserDatastore, auth_required
from flask_wtf import CSRFProtect

from ezrules.backend.forms import OutcomeForm, RuleForm
from ezrules.backend.tasks import app as celery_app
from ezrules.backend.tasks import backtest_rule_change
from ezrules.backend.utils import conditional_decorator
from ezrules.core.application_context import set_organization_id, set_user_list_manager
from ezrules.core.outcomes import DatabaseOutcome
from ezrules.core.rule import Rule, RuleConverter, RuleFactory
from ezrules.core.rule_checkers import (
    OnlyAllowedOutcomesAreReturnedChecker,
    RuleCheckingPipeline,
)
from ezrules.core.rule_updater import (
    RDBRuleEngineConfigProducer,
    RuleManager,
    RuleManagerFactory,
    RuleRevision,
)
from ezrules.core.user_lists import PersistentUserListManager
from ezrules.models.backend_core import Role, RuleBackTestingResult, User
from ezrules.models.backend_core import Rule as RuleModel
from ezrules.models.database import db_session
from ezrules.settings import app_settings

outcome_manager = DatabaseOutcome(db_session=db_session, o_id=app_settings.ORG_ID)
user_list_manager = PersistentUserListManager(db_session=db_session, o_id=app_settings.ORG_ID)

# Initialize application context
set_organization_id(app_settings.ORG_ID)
set_user_list_manager(user_list_manager)

rule_checker = RuleCheckingPipeline(checkers=[OnlyAllowedOutcomesAreReturnedChecker(outcome_manager=outcome_manager)])

app = Flask(__name__)
app.logger.setLevel(logging.INFO)
app.secret_key = app_settings.APP_SECRET
app.config["SECURITY_PASSWORD_SALT"] = os.environ.get(
    "SECURITY_PASSWORD_SALT", "146585145368132386173505678016728509634"
)
app.config["SECURITY_SEND_REGISTER_EMAIL"] = False
app.config["SECURITY_REGISTERABLE"] = True
app.config["TESTING"] = app_settings.TESTING
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0
app.config["EVALUATOR_ENDPOINT"] = app_settings.EVALUATOR_ENDPOINT
bootstrap = Bootstrap5(app)
csrf = CSRFProtect(app)
url_safe_token = secrets.token_urlsafe(16)
app.secret_key = url_safe_token
o_id = app_settings.ORG_ID
fsrm: RuleManager = RuleManagerFactory.get_rule_manager("RDBRuleManager", **{"db": db_session, "o_id": o_id})

app.teardown_appcontext(lambda exc: db_session.close())
user_datastore = SQLAlchemySessionUserDatastore(db_session, User, Role)
app.security = Security(app, user_datastore)  # type: ignore[unresolved-attribute]
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
        new_rule = RuleModel(rid=rule.rid, logic=rule._source, description=rule.description)
        fsrm.save_rule(new_rule)
        app.logger.info("Saving new version of the rules")
        rule_engine_config_producer.save_config(fsrm)
        app.logger.info(rule)
        return redirect(url_for("show_rule", rule_id=new_rule.r_id))


@app.route("/rule/<int:rule_id>/timeline", methods=["GET"])
@conditional_decorator(not app.config["TESTING"], auth_required())
def timeline(rule_id):
    latest_version = cast(RuleModel, fsrm.load_rule(rule_id))
    revision_list = fsrm.get_rule_revision_list(latest_version)
    rules = [fsrm.load_rule(rule_id, revision_number=r.revision_number) for r in revision_list]
    # Add the current version
    rules = [RuleFactory.from_json(r.__dict__) for r in rules]
    revision_list.append(RuleRevision(revision_number=latest_version.version, created=None))
    rules.append(RuleFactory.from_json(latest_version.__dict__))
    logics = [r._source for r in rules]
    diff_timeline = []
    for ct, (l1, l2) in enumerate(zip(logics[:-1], logics[1:], strict=False)):
        diff = difflib.HtmlDiff().make_file(
            fromlines=l1.split("\n"),
            tolines=l2.split("\n"),
            fromdesc=f"Revision {revision_list[ct].revision_number}",
            todesc=f"Revision {revision_list[ct + 1].revision_number}",
        )
        diff_timeline.append(diff)

    return render_template("timeline.html", timeline=diff_timeline, rule=rule_id)


@app.route("/rule/<int:rule_id>", methods=["GET", "POST"])
@app.route("/rule/<int:rule_id>/<revision_number>", methods=["GET"])
@conditional_decorator(not app.config["TESTING"], auth_required())
def show_rule(rule_id: str, revision_number: int | None = None):
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


@app.route("/get_backtesting_results/<int:rule_id>", methods=["GET"])
def get_backtesting_results(rule_id):
    backtesting_results = (
        db_session.query(RuleBackTestingResult)
        .filter(RuleBackTestingResult.r_id == rule_id)
        .order_by(sqlalchemy.desc(RuleBackTestingResult.created_at))
        .limit(3)
    )

    def dslice(d):
        return {k: d[k] for k in d if k in ("task_id", "created_at")}

    return jsonify([dslice(br.__dict__) for br in backtesting_results])


@app.route("/verify_rule", methods=["POST"])
@csrf.exempt
def verifyty_rule():
    source_ = None
    try:
        source_ = request.get_json()["rule_source"]
        rule = Rule(rid="", logic=source_)
    except Exception:
        app.logger.info(f"Failed to compile logic: {source_}")
        return {}
    app.logger.info(f"About to return these params: {rule.get_rule_params()}")
    return jsonify(params=sorted(rule.get_rule_params(), key=str))


@app.route("/test_rule", methods=["POST"])
@csrf.exempt
def test_rule():
    test_json = request.get_json()
    rule_source = test_json["rule_source"]
    print(rule_source)
    try:
        test_object = json.loads(test_json["test_json"])
    except JSONDecodeError:
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
        return render_template("outcomes.html", form=form, outcomes=outcome_manager.get_allowed_outcomes())
    else:
        if form.validate():
            outcome_manager.add_outcome(form.outcome.data)
            return redirect(url_for("verified_outcomes"))


@app.route("/backtesting", methods=["POST"])
@csrf.exempt
def backtesting():
    test_json = request.get_json()
    new_rule_logic = test_json["new_rule_logic"]
    r_id = test_json["r_id"]
    res = backtest_rule_change.apply_async(args=[r_id, new_rule_logic])
    btr = RuleBackTestingResult(r_id=r_id, task_id=res.task_id)
    db_session.add(btr)
    db_session.commit()
    return {"new_rule_logic": new_rule_logic}


@app.route("/get_task_status/<string:task_id>", methods=["GET"])
def get_task_status(task_id: str):
    t = AsyncResult(id=task_id, backend=celery_app.backend)
    ready = t.ready()
    result = t.result if ready else None
    app.logger.info(f"Getting task status for {task_id}: {ready=} with {result=}")
    all_outcomes = set()
    if not ready or result is None:
        return jsonify(ready=ready, result=None)
    for v in result.values():
        for outcome in v:
            all_outcomes.add(outcome)

    df_data = []
    for k in ["Deployed", "Tested"]:
        frame = {}
        if k == "Deployed":
            kk = ["stored_result", "stored_result_rate"]
        else:
            kk = ["proposed_result", "proposed_result_rate"]
        for o in sorted(all_outcomes):
            for kkk in kk:
                if kkk.endswith("_rate"):
                    c = f"{o} rate, %"
                else:
                    c = o
                frame[c] = round(result[kkk].get(o, 0), 3)
        df_data.append(frame)

    df = pd.DataFrame(df_data, index=["Deployed", "Tested"])

    return jsonify(
        ready=ready,
        result=df.to_html(classes="table table-striped table-bordered text-center"),
    )


@app.route("/management/lists", methods=["GET", "POST"])
@conditional_decorator(not app.config["TESTING"], auth_required())
def user_lists():
    if request.method == "POST":
        action = request.form.get("action")

        if action == "create_list":
            list_name = request.form.get("list_name", "").strip()
            if list_name:
                try:
                    user_list_manager.create_list(list_name)
                    flash(f"List '{list_name}' created successfully.", "success")
                except ValueError as e:
                    flash(str(e), "error")
            else:
                flash("List name cannot be empty.", "error")

        elif action == "delete_list":
            list_name = request.form.get("list_name", "").strip()
            if list_name:
                try:
                    user_list_manager.delete_list(list_name)
                    flash(f"List '{list_name}' deleted successfully.", "success")
                except KeyError as e:
                    flash(str(e), "error")

        elif action == "add_entry":
            list_name = request.form.get("list_name", "").strip()
            entry_value = request.form.get("entry_value", "").strip()
            if list_name and entry_value:
                user_list_manager.add_entry(list_name, entry_value)
                flash(f"Added '{entry_value}' to '{list_name}'.", "success")
            else:
                flash("Both list name and entry value are required.", "error")

        elif action == "remove_entry":
            list_name = request.form.get("list_name", "").strip()
            entry_value = request.form.get("entry_value", "").strip()
            if list_name and entry_value:
                try:
                    user_list_manager.remove_entry(list_name, entry_value)
                    flash(f"Removed '{entry_value}' from '{list_name}'.", "success")
                except KeyError as e:
                    flash(str(e), "error")
            else:
                flash("Both list name and entry value are required.", "error")

        return redirect(url_for("user_lists"))

    return render_template("user_lists.html", user_lists=user_list_manager.get_all_entries())


@app.route("/ping", methods=["GET"])
@csrf.exempt
def ping():
    return "OK"
