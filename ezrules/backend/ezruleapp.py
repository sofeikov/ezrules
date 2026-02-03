import datetime
import difflib
import json
import logging
import os
import secrets
from json.decoder import JSONDecodeError
from typing import cast

import pandas as pd
import sqlalchemy
import sqlalchemy.exc
from celery.result import AsyncResult
from flask import (
    Flask,
    Response,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_bootstrap import Bootstrap5
from flask_cors import CORS
from flask_security import Security, SQLAlchemySessionUserDatastore, auth_required, current_user
from flask_security.utils import hash_password
from flask_wtf import CSRFProtect

from ezrules.backend.analytics import AGGREGATION_CONFIG, get_bucket_expression
from ezrules.backend.forms import CSVUploadForm, LabelForm, OutcomeForm, RoleForm, RuleForm, UserForm, UserRoleForm
from ezrules.backend.label_upload_service import LabelUploadService
from ezrules.backend.tasks import app as celery_app
from ezrules.backend.tasks import backtest_rule_change
from ezrules.backend.utils import conditional_decorator
from ezrules.core.application_context import set_organization_id, set_user_list_manager
from ezrules.core.labels import DatabaseLabelManager
from ezrules.core.outcomes import DatabaseOutcome
from ezrules.core.permissions import PermissionManager, requires_permission
from ezrules.core.permissions_constants import PermissionAction
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
from ezrules.models.backend_core import (
    Action,
    Label,
    Role,
    RoleActions,
    RuleBackTestingResult,
    RuleEngineConfigHistory,
    RuleHistory,
    TestingRecordLog,
    TestingResultsLog,
    User,
)
from ezrules.models.backend_core import Rule as RuleModel
from ezrules.models.database import db_session
from ezrules.settings import app_settings

outcome_manager = DatabaseOutcome(db_session=db_session, o_id=app_settings.ORG_ID)
label_manager = DatabaseLabelManager(db_session=db_session, o_id=app_settings.ORG_ID)
user_list_manager = PersistentUserListManager(db_session=db_session, o_id=app_settings.ORG_ID)

# Initialize application context
set_organization_id(app_settings.ORG_ID)
set_user_list_manager(user_list_manager)

rule_checker = RuleCheckingPipeline(checkers=[OnlyAllowedOutcomesAreReturnedChecker(outcome_manager=outcome_manager)])

app = Flask(__name__)
CORS(app)  # Enable CORS for Angular frontend
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
@conditional_decorator(not app.config["TESTING"], requires_permission(PermissionAction.VIEW_RULES))
def rules():
    rules = fsrm.load_all_rules()
    return render_template("rules.html", rules=rules, evaluator_endpoint=app.config["EVALUATOR_ENDPOINT"])


@app.route("/api/rules", methods=["GET"])
@csrf.exempt
def api_rules():
    """API endpoint to get all rules as JSON for Angular frontend."""
    rules = fsrm.load_all_rules()
    rules_data = [
        {
            "r_id": rule.r_id,
            "rid": rule.rid,
            "description": rule.description,
            "logic": rule.logic,
            "created_at": rule.created_at.isoformat() if rule.created_at else None,  # type: ignore[union-attr]
        }
        for rule in rules
    ]
    return jsonify({"rules": rules_data, "evaluator_endpoint": app.config["EVALUATOR_ENDPOINT"]})


@app.route("/api/rules/<int:rule_id>", methods=["GET"])
@csrf.exempt
def api_rule_detail(rule_id: int):
    """API endpoint to get a single rule's details as JSON for Angular frontend."""
    rule = fsrm.load_rule(rule_id)  # type: ignore[arg-type]
    if rule is None:
        return jsonify({"error": "Rule not found"}), 404

    revision_list = fsrm.get_rule_revision_list(rule)
    revisions_data = [
        {
            "revision_number": rev.revision_number,
            "created_at": rev.created.isoformat() if rev.created else None,
        }
        for rev in revision_list
    ]

    rule_data = {
        "r_id": rule.r_id,
        "rid": rule.rid,
        "description": rule.description,
        "logic": rule.logic,
        "created_at": rule.created_at.isoformat() if rule.created_at else None,  # type: ignore[union-attr]
        "revisions": revisions_data,
    }
    return jsonify(rule_data)


@app.route("/api/rules/<int:rule_id>/revisions/<int:revision_number>", methods=["GET"])
@csrf.exempt
def api_rule_revision(rule_id: int, revision_number: int):
    """API endpoint to get a specific historical revision of a rule."""
    try:
        rule = fsrm.load_rule(rule_id, revision_number=revision_number)  # type: ignore[arg-type]
    except sqlalchemy.exc.NoResultFound:
        return jsonify({"error": "Rule or revision not found"}), 404

    rule_data = {
        "r_id": rule_id,
        "rid": rule.rid,
        "description": rule.description,
        "logic": rule.logic,
        "created_at": rule.created_at.isoformat() if rule.created_at else None,  # type: ignore[union-attr]
        "revision_number": revision_number,
        "revisions": [],
    }
    return jsonify(rule_data)


HISTORY_LIMIT_DEFAULT = 10


@app.route("/api/rules/<int:rule_id>/history", methods=["GET"])
@csrf.exempt
def api_rule_history(rule_id: int):
    """API endpoint to get the ordered logic history for a rule (for diff timeline).

    Returns up to HISTORY_LIMIT_DEFAULT most recent revisions plus the current version.
    The limit can be overridden via the ?limit= query parameter.
    """
    limit = request.args.get("limit", HISTORY_LIMIT_DEFAULT, type=int)

    latest_version = fsrm.load_rule(rule_id)  # type: ignore[arg-type]
    if latest_version is None:
        return jsonify({"error": "Rule not found"}), 404

    revision_list = fsrm.get_rule_revision_list(latest_version)

    # Take only the most recent `limit` revisions (revision_list is oldest-first)
    trimmed_revisions = revision_list[-limit:] if len(revision_list) > limit else revision_list

    history: list[dict] = []
    for rev in trimmed_revisions:
        try:
            rule = fsrm.load_rule(rule_id, revision_number=rev.revision_number)  # type: ignore[arg-type]
        except sqlalchemy.exc.NoResultFound:
            continue
        history.append(
            {
                "revision_number": rev.revision_number,
                "logic": rule.logic,
                "description": rule.description,
                "created_at": rev.created.isoformat() if rev.created else None,
            }
        )

    # Append the current (latest) version
    history.append(
        {
            "revision_number": latest_version.version,  # type: ignore[attr-defined]
            "logic": latest_version.logic,
            "description": latest_version.description,
            "created_at": latest_version.created_at.isoformat() if latest_version.created_at else None,  # type: ignore[union-attr]
            "is_current": True,
        }
    )

    return jsonify(
        {
            "r_id": rule_id,
            "rid": latest_version.rid,
            "history": history,
        }
    )


@app.route("/api/rules/<int:rule_id>", methods=["PUT"])
@csrf.exempt
def api_update_rule(rule_id: int):
    """API endpoint to update a rule for Angular frontend."""
    rule = fsrm.load_rule(rule_id)  # type: ignore[arg-type]
    if rule is None:
        return jsonify({"success": False, "error": "Rule not found"}), 404

    data = request.get_json()
    if data is None:
        return jsonify({"success": False, "error": "No data provided"}), 400

    description = data.get("description", rule.description)
    logic = data.get("logic", rule.logic)

    # Validate the rule logic by trying to compile it
    try:
        rule_config = {"rid": rule.rid, "logic": logic, "description": description}
        RuleFactory.from_json(rule_config)
    except Exception as e:
        return jsonify({"success": False, "error": f"Invalid rule logic: {str(e)}"}), 400

    # Update the rule
    rule.description = description
    rule.logic = logic
    fsrm.save_rule(rule)

    # Update rule engine config
    app.logger.info("Saving new version of the rules via API")
    rule_engine_config_producer.save_config(fsrm)

    # Get updated revision list
    revision_list = fsrm.get_rule_revision_list(rule)
    revisions_data = [
        {
            "revision_number": rev.revision_number,
            "created_at": rev.created.isoformat() if rev.created else None,
        }
        for rev in revision_list
    ]

    rule_data = {
        "r_id": rule.r_id,
        "rid": rule.rid,
        "description": rule.description,
        "logic": rule.logic,
        "created_at": rule.created_at.isoformat() if rule.created_at else None,  # type: ignore[union-attr]
        "revisions": revisions_data,
    }

    return jsonify({"success": True, "message": "Rule updated successfully", "rule": rule_data})


@app.route("/create_rule", methods=["GET", "POST"])
@conditional_decorator(not app.config["TESTING"], auth_required())
@conditional_decorator(not app.config["TESTING"], requires_permission(PermissionAction.CREATE_RULE))
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
@conditional_decorator(not app.config["TESTING"], requires_permission(PermissionAction.VIEW_RULES))
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
@conditional_decorator(not app.config["TESTING"], requires_permission(PermissionAction.VIEW_RULES))
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
        if not app.config.get("TESTING", False):
            if not PermissionManager.user_has_permission(current_user, PermissionAction.MODIFY_RULE, int(rule_id)):
                abort(403)

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
@conditional_decorator(not app.config["TESTING"], requires_permission(PermissionAction.VIEW_OUTCOMES))
def verified_outcomes():
    form = OutcomeForm()
    if request.method == "GET":
        return render_template("outcomes.html", form=form, outcomes=outcome_manager.get_allowed_outcomes())
    else:
        # Check if this is a delete action
        if request.form.get("action") == "delete":
            if not app.config.get("TESTING", False):
                if not PermissionManager.user_has_permission(current_user, PermissionAction.DELETE_OUTCOME):
                    abort(403)

            outcome_to_delete = request.form.get("outcome")
            if outcome_to_delete:
                outcome_manager.remove_outcome(outcome_to_delete)
            return redirect(url_for("verified_outcomes"))

        # Otherwise, it's an add action
        if not app.config.get("TESTING", False):
            if not PermissionManager.user_has_permission(current_user, PermissionAction.CREATE_OUTCOME):
                abort(403)

        if form.validate():
            outcome_manager.add_outcome(form.outcome.data)
            return redirect(url_for("verified_outcomes"))
        else:
            return render_template("outcomes.html", form=form, outcomes=outcome_manager.get_allowed_outcomes())


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


@app.route("/management/labels", methods=["GET", "POST"])
@conditional_decorator(not app.config["TESTING"], auth_required())
@conditional_decorator(not app.config["TESTING"], requires_permission(PermissionAction.VIEW_LABELS))
def label_management():
    form = LabelForm()
    if request.method == "GET":
        return render_template("labels.html", form=form, labels=label_manager.get_all_labels())
    else:
        # Check if this is a delete action
        if request.form.get("action") == "delete":
            if not app.config.get("TESTING", False):
                if not PermissionManager.user_has_permission(current_user, PermissionAction.DELETE_LABEL):
                    abort(403)

            label_to_delete = request.form.get("label")
            if label_to_delete:
                label_manager.remove_label(label_to_delete)
            return redirect(url_for("label_management"))

        # Otherwise, it's an add action
        if not app.config.get("TESTING", False):
            if not PermissionManager.user_has_permission(current_user, PermissionAction.CREATE_LABEL):
                abort(403)

        if form.validate():
            label_manager.add_label(form.label.data)
            return redirect(url_for("label_management"))
        else:
            return render_template("labels.html", form=form, labels=label_manager.get_all_labels())


@app.route("/upload_labels", methods=["GET", "POST"])
@conditional_decorator(not app.config["TESTING"], auth_required())
@conditional_decorator(not app.config["TESTING"], requires_permission(PermissionAction.CREATE_LABEL))
def upload_labels():
    form = CSVUploadForm()
    if request.method == "GET":
        return render_template("upload_labels.html", form=form)
    elif request.method == "POST":
        if form.validate():
            csv_file = form.csv_file.data

            try:
                # Read CSV content
                csv_content = csv_file.read().decode("utf-8")

                # Use the service to process the upload
                upload_service = LabelUploadService(db_session)
                result = upload_service.upload_labels_from_csv(csv_content)

                # Commit all changes if any were successful
                if result.success_count > 0:
                    db_session.commit()
                    flash(f"Successfully processed {result.success_count} labels.", "success")

                if result.error_count > 0:
                    flash(f"Failed to process {result.error_count} rows. Check the errors below.", "warning")
                    for error in result.errors[:10]:  # Show first 10 errors
                        flash(error, "error")
                    if len(result.errors) > 10:
                        flash(f"... and {len(result.errors) - 10} more errors", "error")

                if result.success_count == 0 and result.error_count == 0:
                    flash("CSV file was empty or contained no valid data.", "warning")

            except Exception as e:
                db_session.rollback()
                flash(f"Error processing CSV file: {str(e)}", "error")

            return redirect(url_for("upload_labels"))
        else:
            return render_template("upload_labels.html", form=form)


@app.route("/labels", methods=["GET", "POST"])
@csrf.exempt
def label():
    if request.method == "GET":
        labels = db_session.query(Label).all()
        return jsonify([label.label for label in labels])
    elif request.method == "POST":
        label_names = request.get_json()["label_name"]
        if isinstance(label_names, str):
            label_names = [label_names]
        failed_to_add = []
        for ln in label_names:
            label = Label(label=ln)
            try:
                db_session.add(label)
                db_session.commit()
            except sqlalchemy.exc.IntegrityError:
                db_session.rollback()
                failed_to_add.append(ln)
        return jsonify(response="OK", failed_to_add=failed_to_add)


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
@conditional_decorator(not app.config["TESTING"], requires_permission(PermissionAction.VIEW_LISTS))
def user_lists():
    if request.method == "POST":
        action = request.form.get("action")

        if action == "create_list":
            if not app.config.get("TESTING", False):
                if not PermissionManager.user_has_permission(current_user, PermissionAction.CREATE_LIST):
                    abort(403)

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
            if not app.config.get("TESTING", False):
                if not PermissionManager.user_has_permission(current_user, PermissionAction.DELETE_LIST):
                    abort(403)

            list_name = request.form.get("list_name", "").strip()
            if list_name:
                try:
                    user_list_manager.delete_list(list_name)
                    flash(f"List '{list_name}' deleted successfully.", "success")
                except KeyError as e:
                    flash(str(e), "error")

        elif action == "add_entry":
            if not app.config.get("TESTING", False):
                if not PermissionManager.user_has_permission(current_user, PermissionAction.MODIFY_LIST):
                    abort(403)

            list_name = request.form.get("list_name", "").strip()
            entry_value = request.form.get("entry_value", "").strip()
            if list_name and entry_value:
                user_list_manager.add_entry(list_name, entry_value)
                flash(f"Added '{entry_value}' to '{list_name}'.", "success")
            else:
                flash("Both list name and entry value are required.", "error")

        elif action == "remove_entry":
            if not app.config.get("TESTING", False):
                if not PermissionManager.user_has_permission(current_user, PermissionAction.MODIFY_LIST):
                    abort(403)

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


@app.route("/audit", methods=["GET"])
@conditional_decorator(not app.config["TESTING"], auth_required())
@conditional_decorator(not app.config["TESTING"], requires_permission(PermissionAction.ACCESS_AUDIT_TRAIL))
def audit_trail():
    rule_history = db_session.query(RuleHistory).order_by(RuleHistory.changed.desc()).limit(100).all()
    config_history = (
        db_session.query(RuleEngineConfigHistory).order_by(RuleEngineConfigHistory.changed.desc()).limit(100).all()
    )

    return render_template("audit_trail.html", rule_history=rule_history, config_history=config_history)


@app.route("/management/users", methods=["GET", "POST"])
@conditional_decorator(not app.config["TESTING"], auth_required())
@conditional_decorator(not app.config["TESTING"], requires_permission(PermissionAction.VIEW_USERS))
def user_management():
    form = UserForm()

    # Populate role choices
    roles = db_session.query(Role).all()
    role_choices = [("", "No role assigned")] + [(role.name, f"{role.name} - {role.description}") for role in roles]
    form.role_name.choices = role_choices

    if request.method == "POST":
        if not app.config.get("TESTING", False):
            if not PermissionManager.user_has_permission(current_user, PermissionAction.CREATE_USER):
                abort(403)

        if form.validate_on_submit():
            user_email = form.user_email.data.strip()
            password = form.password.data.strip()
            role_name = form.role_name.data.strip() if form.role_name.data else None

            try:
                # Check if user already exists
                existing_user = db_session.query(User).filter_by(email=user_email).first()
                if existing_user:
                    flash(f"User with email {user_email} already exists.", "error")
                    return redirect(url_for("user_management"))

                # Create new user
                hashed_password = hash_password(password)
                new_user = User(
                    email=user_email,
                    password=hashed_password,
                    active=True,
                    fs_uniquifier=user_email,
                )
                db_session.add(new_user)

                # Add role if specified
                if role_name:
                    role = db_session.query(Role).filter_by(name=role_name).first()
                    if role:
                        new_user.roles.append(role)
                    else:
                        flash(f"Role '{role_name}' not found.", "warning")

                db_session.commit()
                flash(f"User {user_email} created successfully.", "success")
            except Exception as e:
                db_session.rollback()
                flash(f"Error creating user: {str(e)}", "error")

            return redirect(url_for("user_management"))

    # GET request - show user management page
    users = db_session.query(User).all()
    return render_template("user_management.html", users=users, form=form)


@app.route("/role_management", methods=["GET", "POST"])
@conditional_decorator(not app.config["TESTING"], auth_required())
@conditional_decorator(not app.config["TESTING"], requires_permission(PermissionAction.VIEW_ROLES))
def role_management():
    role_form = RoleForm()
    user_role_form = UserRoleForm()

    # Populate choices for user-role assignment
    users = db_session.query(User).all()
    roles = db_session.query(Role).all()
    user_role_form.user_id.choices = [(user.id, user.email) for user in users]
    user_role_form.role_id.choices = [(role.id, role.name) for role in roles]

    if request.method == "POST":
        # Handle role creation
        if "create_role" in request.form:
            if not app.config.get("TESTING", False):
                if not PermissionManager.user_has_permission(current_user, PermissionAction.CREATE_ROLE):
                    abort(403)

            if role_form.validate_on_submit():
                role_name = role_form.name.data.strip()
                description = role_form.description.data.strip() if role_form.description.data else ""

                try:
                    # Check if role already exists
                    existing_role = db_session.query(Role).filter_by(name=role_name).first()
                    if existing_role:
                        flash(f"Role '{role_name}' already exists.", "error")
                        return redirect(url_for("role_management"))

                    # Create new role
                    new_role = Role(name=role_name, description=description)
                    db_session.add(new_role)
                    db_session.commit()
                    flash(f"Role '{role_name}' created successfully.", "success")
                except Exception as e:
                    db_session.rollback()
                    flash(f"Error creating role: {str(e)}", "error")

                return redirect(url_for("role_management"))

        # Handle user-role assignment
        elif "assign_role" in request.form:
            if not app.config.get("TESTING", False):
                if not PermissionManager.user_has_permission(current_user, PermissionAction.MODIFY_ROLE):
                    abort(403)

            if user_role_form.validate_on_submit():
                user_id = user_role_form.user_id.data
                role_id = user_role_form.role_id.data

                try:
                    user = db_session.query(User).get(user_id)
                    role = db_session.query(Role).get(role_id)

                    if not user or not role:
                        flash("User or role not found.", "error")
                        return redirect(url_for("role_management"))

                    # Check if user already has this role
                    if role in user.roles:
                        flash(f"User '{user.email}' already has role '{role.name}'.", "warning")
                        return redirect(url_for("role_management"))

                    # Assign role to user
                    user.roles.append(role)
                    db_session.commit()
                    flash(f"Role '{role.name}' assigned to user '{user.email}' successfully.", "success")
                except Exception as e:
                    db_session.rollback()
                    flash(f"Error assigning role: {str(e)}", "error")

                return redirect(url_for("role_management"))

    # GET request - show role management page
    all_roles = db_session.query(Role).all()
    all_users = db_session.query(User).all()
    return render_template(
        "role_management.html", roles=all_roles, users=all_users, role_form=role_form, user_role_form=user_role_form
    )


@app.route("/role_permissions/<int:role_id>", methods=["GET", "POST"])
@conditional_decorator(not app.config["TESTING"], auth_required())
@conditional_decorator(not app.config["TESTING"], requires_permission(PermissionAction.MANAGE_PERMISSIONS))
def manage_role_permissions(role_id):
    role = db_session.query(Role).get(role_id)
    if not role:
        abort(404)
    all_actions = db_session.query(Action).all()

    # Get current permissions for this role
    current_permissions = db_session.query(RoleActions).filter_by(role_id=role_id).all()
    current_action_ids = {rp.action_id for rp in current_permissions}

    if request.method == "POST":
        if not app.config.get("TESTING", False):
            if not PermissionManager.user_has_permission(current_user, PermissionAction.MANAGE_PERMISSIONS):
                abort(403)

        try:
            # Get selected permissions from form
            selected_action_ids = set()
            for action in all_actions:
                if request.form.get(f"action_{action.id}"):
                    selected_action_ids.add(action.id)

            # Remove permissions that are no longer selected
            for permission in current_permissions:
                if permission.action_id not in selected_action_ids:
                    db_session.delete(permission)

            # Add new permissions
            for action_id in selected_action_ids:
                if action_id not in current_action_ids:
                    new_permission = RoleActions(role_id=role_id, action_id=action_id)
                    db_session.add(new_permission)

            db_session.commit()
            flash(f"Permissions updated for role '{role.name}'.", "success")
        except Exception as e:
            db_session.rollback()
            flash(f"Error updating permissions: {str(e)}", "error")

        return redirect(url_for("manage_role_permissions", role_id=role_id))

    return render_template(
        "role_permissions.html", role=role, actions=all_actions, current_action_ids=current_action_ids
    )


@app.route("/delete_role/<int:role_id>", methods=["POST"])
@conditional_decorator(not app.config["TESTING"], auth_required())
@conditional_decorator(not app.config["TESTING"], requires_permission(PermissionAction.DELETE_ROLE))
def delete_role(role_id):
    try:
        role = db_session.query(Role).get(role_id)
        if not role:
            abort(404)

        # Check if role is assigned to any users
        if role.users.count() > 0:
            flash(f"Cannot delete role '{role.name}' - it is assigned to {role.users.count()} user(s).", "error")
            return redirect(url_for("role_management"))

        # Delete role permissions first
        db_session.query(RoleActions).filter_by(role_id=role_id).delete()

        # Delete the role
        db_session.delete(role)
        db_session.commit()
        flash(f"Role '{role.name}' deleted successfully.", "success")
    except Exception as e:
        db_session.rollback()
        flash(f"Error deleting role: {str(e)}", "error")

    return redirect(url_for("role_management"))


@app.route("/remove_user_role/<int:user_id>/<int:role_id>", methods=["POST"])
@conditional_decorator(not app.config["TESTING"], auth_required())
@conditional_decorator(not app.config["TESTING"], requires_permission(PermissionAction.MODIFY_ROLE))
def remove_user_role(user_id, role_id):
    try:
        user = db_session.query(User).get(user_id)
        role = db_session.query(Role).get(role_id)
        if not user or not role:
            abort(404)

        if role in user.roles:
            user.roles.remove(role)
            db_session.commit()
            flash(f"Role '{role.name}' removed from user '{user.email}' successfully.", "success")
        else:
            flash(f"User '{user.email}' does not have role '{role.name}'.", "warning")
    except Exception as e:
        db_session.rollback()
        flash(f"Error removing role: {str(e)}", "error")

    return redirect(url_for("role_management"))


@app.route("/mark-event", methods=["POST"])
@csrf.exempt
def mark_event():
    """Mark an event with a label for analytics purposes."""
    request_data = request.get_json(silent=True)

    if request_data is None:
        return jsonify({"error": "JSON data required"}), 400

    event_id = request_data.get("event_id")
    label_name = request_data.get("label_name")

    if not event_id or not label_name:
        return jsonify({"error": "event_id and label_name are required"}), 400

    try:
        # Find the event by event_id
        event_record = db_session.query(TestingRecordLog).filter_by(event_id=event_id).first()
        if not event_record:
            return jsonify({"error": f"Event with id '{event_id}' not found"}), 404

        # Find the label by name
        label = db_session.query(Label).filter_by(label=label_name.strip().upper()).first()
        if not label:
            return jsonify({"error": f"Label '{label_name}' not found"}), 404

        # Update the event record with the label
        event_record.el_id = label.el_id
        db_session.commit()

        return jsonify(
            {
                "message": f"Event '{event_id}' successfully marked with label '{label_name}'",
                "event_id": event_id,
                "label_name": label_name,
            }
        ), 200

    except Exception as e:
        db_session.rollback()
        return jsonify({"error": f"Database error: {str(e)}"}), 500


@app.route("/ping", methods=["GET"])
@csrf.exempt
def ping():
    return "OK"


@app.route("/dashboard", methods=["GET"])
@conditional_decorator(not app.config["TESTING"], auth_required())
@conditional_decorator(not app.config["TESTING"], requires_permission(PermissionAction.VIEW_RULES))
def dashboard():
    """Display dashboard with key metrics."""
    # Count active rules
    active_rules_count = db_session.query(RuleModel).count()

    return render_template(
        "dashboard.html",
        active_rules_count=active_rules_count,
    )


@app.route("/label_analytics", methods=["GET"])
@conditional_decorator(not app.config["TESTING"], auth_required())
@conditional_decorator(not app.config["TESTING"], requires_permission(PermissionAction.VIEW_LABELS))
def label_analytics():
    """Display label analytics dashboard with key metrics."""
    return render_template("label_analytics.html")


@app.route("/api/transaction_volume", methods=["GET"])
@csrf.exempt
def transaction_volume():
    """API endpoint to get transaction volume data for various time aggregations."""
    aggregation = request.args.get("aggregation", "1h")

    if aggregation not in AGGREGATION_CONFIG:
        return jsonify({"error": "Invalid aggregation"}), 400

    config = AGGREGATION_CONFIG[aggregation]
    start_time = datetime.datetime.now() - config["delta"]

    # Build bucket expression using shared helper
    bucket_expr = get_bucket_expression(config, TestingRecordLog.created_at)

    transactions = (
        db_session.query(bucket_expr.label("bucket"), sqlalchemy.func.count(TestingRecordLog.tl_id).label("count"))
        .filter(TestingRecordLog.created_at >= start_time)
        .group_by("bucket")
        .order_by("bucket")
        .all()
    )

    # Format data for Chart.js
    labels = []
    data = []

    for bucket, count in transactions:
        if config["use_date_trunc"]:
            labels.append(bucket.strftime(config["label_format"]))
        else:
            dt = datetime.datetime.fromtimestamp(bucket)
            labels.append(dt.strftime(config["label_format"]))
        data.append(count)

    return jsonify({"labels": labels, "data": data, "aggregation": aggregation})


@app.route("/api/outcomes_distribution", methods=["GET"])
@csrf.exempt
def outcomes_distribution():
    """API endpoint to get temporal distribution of rule outcomes for various time aggregations."""
    aggregation = request.args.get("aggregation", "1h")

    if aggregation not in AGGREGATION_CONFIG:
        return jsonify({"error": "Invalid aggregation"}), 400

    config = AGGREGATION_CONFIG[aggregation]
    start_time = datetime.datetime.now() - config["delta"]

    # Build bucket expression using shared helper
    bucket_expr = get_bucket_expression(config, TestingRecordLog.created_at)

    # Query outcomes distribution over time
    outcomes = (
        db_session.query(
            bucket_expr.label("bucket"),
            TestingResultsLog.rule_result,
            sqlalchemy.func.count(TestingResultsLog.rule_result).label("count"),
        )
        .join(TestingRecordLog, TestingRecordLog.tl_id == TestingResultsLog.tl_id)
        .filter(TestingRecordLog.created_at >= start_time)
        .group_by("bucket", TestingResultsLog.rule_result)
        .order_by("bucket")
        .all()
    )

    # Get unique outcome labels
    outcome_labels = set()
    for _bucket, outcome, _count in outcomes:
        outcome_labels.add(outcome)
    outcome_labels = sorted(outcome_labels)

    # Organize data by time bucket
    time_buckets = {}
    for bucket, outcome, count in outcomes:
        if bucket not in time_buckets:
            time_buckets[bucket] = {}
        time_buckets[bucket][outcome] = count

    # Format data for Chart.js line chart with multiple datasets
    labels = []
    datasets = {outcome: [] for outcome in outcome_labels}

    sorted_buckets = sorted(time_buckets.keys())
    for bucket in sorted_buckets:
        if config["use_date_trunc"]:
            labels.append(bucket.strftime(config["label_format"]))
        else:
            dt = datetime.datetime.fromtimestamp(bucket)
            labels.append(dt.strftime(config["label_format"]))

        # Add count for each outcome (0 if not present in this bucket)
        for outcome in outcome_labels:
            datasets[outcome].append(time_buckets[bucket].get(outcome, 0))

    # Format datasets for Chart.js
    chart_datasets = []
    colors = [
        {"border": "rgb(255, 99, 132)", "background": "rgba(255, 99, 132, 0.1)"},
        {"border": "rgb(54, 162, 235)", "background": "rgba(54, 162, 235, 0.1)"},
        {"border": "rgb(255, 206, 86)", "background": "rgba(255, 206, 86, 0.1)"},
        {"border": "rgb(75, 192, 192)", "background": "rgba(75, 192, 192, 0.1)"},
        {"border": "rgb(153, 102, 255)", "background": "rgba(153, 102, 255, 0.1)"},
        {"border": "rgb(255, 159, 64)", "background": "rgba(255, 159, 64, 0.1)"},
        {"border": "rgb(201, 203, 207)", "background": "rgba(201, 203, 207, 0.1)"},
    ]

    for idx, outcome in enumerate(outcome_labels):
        color = colors[idx % len(colors)]
        chart_datasets.append(
            {
                "label": outcome,
                "data": datasets[outcome],
                "borderColor": color["border"],
                "backgroundColor": color["background"],
                "tension": 0.3,
                "fill": True,
            }
        )

    return jsonify({"labels": labels, "datasets": chart_datasets, "aggregation": aggregation})


@app.route("/api/labels_distribution", methods=["GET"])
@csrf.exempt
def labels_distribution():
    """API endpoint to get temporal distribution of labels for various time aggregations."""
    aggregation = request.args.get("aggregation", "1h")

    if aggregation not in AGGREGATION_CONFIG:
        return jsonify({"error": "Invalid aggregation"}), 400

    config = AGGREGATION_CONFIG[aggregation]
    start_time = datetime.datetime.now() - config["delta"]

    # Build bucket expression using shared helper
    bucket_expr = get_bucket_expression(config, TestingRecordLog.created_at)

    # Query labels distribution over time (only labeled events)
    labels_data = (
        db_session.query(
            bucket_expr.label("bucket"),
            Label.label,
            sqlalchemy.func.count(Label.label).label("count"),
        )
        .join(TestingRecordLog, TestingRecordLog.el_id == Label.el_id)
        .filter(TestingRecordLog.created_at >= start_time)
        .filter(TestingRecordLog.el_id.isnot(None))
        .group_by("bucket", Label.label)
        .order_by("bucket")
        .all()
    )

    # Get unique label names
    label_names = set()
    for _bucket, label_name, _count in labels_data:
        label_names.add(label_name)
    label_names = sorted(label_names)

    # Organize data by time bucket
    time_buckets = {}
    for bucket, label_name, count in labels_data:
        if bucket not in time_buckets:
            time_buckets[bucket] = {}
        time_buckets[bucket][label_name] = count

    # Format data for Chart.js line chart with multiple datasets
    labels = []
    datasets = {label_name: [] for label_name in label_names}

    sorted_buckets = sorted(time_buckets.keys())
    for bucket in sorted_buckets:
        if config["use_date_trunc"]:
            labels.append(bucket.strftime(config["label_format"]))
        else:
            dt = datetime.datetime.fromtimestamp(bucket)
            labels.append(dt.strftime(config["label_format"]))

        # Add count for each label (0 if not present in this bucket)
        for label_name in label_names:
            datasets[label_name].append(time_buckets[bucket].get(label_name, 0))

    # Format datasets for Chart.js
    chart_datasets = []
    colors = [
        {"border": "rgb(255, 99, 132)", "background": "rgba(255, 99, 132, 0.1)"},
        {"border": "rgb(54, 162, 235)", "background": "rgba(54, 162, 235, 0.1)"},
        {"border": "rgb(255, 206, 86)", "background": "rgba(255, 206, 86, 0.1)"},
        {"border": "rgb(75, 192, 192)", "background": "rgba(75, 192, 192, 0.1)"},
        {"border": "rgb(153, 102, 255)", "background": "rgba(153, 102, 255, 0.1)"},
        {"border": "rgb(255, 159, 64)", "background": "rgba(255, 159, 64, 0.1)"},
        {"border": "rgb(201, 203, 207)", "background": "rgba(201, 203, 207, 0.1)"},
    ]

    for idx, label_name in enumerate(label_names):
        color = colors[idx % len(colors)]
        chart_datasets.append(
            {
                "label": label_name,
                "data": datasets[label_name],
                "borderColor": color["border"],
                "backgroundColor": color["background"],
                "tension": 0.3,
                "fill": True,
            }
        )

    return jsonify({"labels": labels, "datasets": chart_datasets, "aggregation": aggregation})


@app.route("/api/labeled_transaction_volume", methods=["GET"])
@csrf.exempt
def labeled_transaction_volume():
    """API endpoint to get labeled transaction volume data for various time aggregations."""
    aggregation = request.args.get("aggregation", "1h")

    if aggregation not in AGGREGATION_CONFIG:
        return jsonify({"error": "Invalid aggregation"}), 400

    config = AGGREGATION_CONFIG[aggregation]
    start_time = datetime.datetime.now() - config["delta"]

    # Build bucket expression using shared helper
    bucket_expr = get_bucket_expression(config, TestingRecordLog.created_at)

    # Query only labeled transactions
    transactions = (
        db_session.query(bucket_expr.label("bucket"), sqlalchemy.func.count(TestingRecordLog.tl_id).label("count"))
        .filter(TestingRecordLog.created_at >= start_time)
        .filter(TestingRecordLog.el_id.isnot(None))
        .group_by("bucket")
        .order_by("bucket")
        .all()
    )

    # Format data for Chart.js
    labels = []
    data = []

    for bucket, count in transactions:
        if config["use_date_trunc"]:
            labels.append(bucket.strftime(config["label_format"]))
        else:
            dt = datetime.datetime.fromtimestamp(bucket)
            labels.append(dt.strftime(config["label_format"]))
        data.append(count)

    return jsonify({"labels": labels, "data": data, "aggregation": aggregation})


@app.route("/api/labels_summary", methods=["GET"])
@csrf.exempt
def labels_summary():
    """API endpoint to get summary statistics for labels."""
    # Total labeled events
    total_labeled = (
        db_session.query(sqlalchemy.func.count(TestingRecordLog.tl_id))
        .filter(TestingRecordLog.el_id.isnot(None))
        .scalar()
    )

    # Label distribution (pie chart data)
    label_counts = (
        db_session.query(Label.label, sqlalchemy.func.count(TestingRecordLog.tl_id).label("count"))
        .join(TestingRecordLog, TestingRecordLog.el_id == Label.el_id)
        .filter(TestingRecordLog.el_id.isnot(None))
        .group_by(Label.label)
        .order_by(sqlalchemy.desc("count"))
        .all()
    )

    # Format for pie chart
    pie_labels = []
    pie_data = []
    colors = [
        "rgb(255, 99, 132)",
        "rgb(54, 162, 235)",
        "rgb(255, 206, 86)",
        "rgb(75, 192, 192)",
        "rgb(153, 102, 255)",
        "rgb(255, 159, 64)",
        "rgb(201, 203, 207)",
    ]

    for label_name, count in label_counts:
        pie_labels.append(label_name)
        pie_data.append(count)

    return jsonify(
        {
            "total_labeled": total_labeled,
            "pie_chart": {
                "labels": pie_labels,
                "data": pie_data,
                "backgroundColor": colors[: len(pie_labels)],
            },
        }
    )
