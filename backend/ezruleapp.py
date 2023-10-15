import difflib
import secrets
import os

from flask import Flask, render_template, Response, redirect, url_for
from flask import request
from flask_bootstrap import Bootstrap5
from flask_wtf import FlaskForm, CSRFProtect
from wtforms import StringField, SubmitField, Field, TextAreaField
from wtforms.validators import DataRequired
from wtforms.widgets import TextInput

from core.rule import RuleFactory, RuleConverter
from core.rule_updater import (
    RuleManagerFactory,
    RuleDoesNotExistInTheStorage,
    RuleEngineConfigProducer,
)
from core.rule_locker import DynamoDBStorageLocker

rule_locker = DynamoDBStorageLocker(
    table_name=os.environ["DYNAMODB_RULE_LOCKER_TABLE_NAME"]
)

app = Flask(__name__)
app.secret_key = os.environ["APP_SECRET"]
# Bootstrap-Flask requires this line
bootstrap = Bootstrap5(app)
# Flask-WTF requires this line
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


class TagListField(Field):
    widget = TextInput()

    def _value(self):
        if self.data:
            return ", ".join(self.data)
        else:
            return ""

    def process_formdata(self, valuelist):
        if valuelist:
            self.data = [x.strip() for x in valuelist[0].split(",")]
        else:
            self.data = []


class BetterTagListField(TagListField):
    def __init__(self, label="", validators=None, remove_duplicates=True, **kwargs):
        super(BetterTagListField, self).__init__(label, validators, **kwargs)
        self.remove_duplicates = remove_duplicates

    def process_formdata(self, valuelist):
        super(BetterTagListField, self).process_formdata(valuelist)
        if self.remove_duplicates:
            self.data = list(self._remove_duplicates(self.data))

    @classmethod
    def _remove_duplicates(cls, seq):
        """Remove duplicates in a case-insensitive, but case preserving manner"""
        d = {}
        for item in seq:
            if item.lower() not in d:
                d[item.lower()] = True
                yield item


class RuleForm(FlaskForm):
    rid = StringField("A Unique rule ID", validators=[DataRequired()])
    description = StringField("Rule description")
    logic = TextAreaField("Rule logic", validators=[DataRequired()])
    tags = BetterTagListField("Rule tags")
    params = BetterTagListField("Rule params")
    submit = SubmitField("Submit")


@app.route("/create_rule", methods=["GET", "POST"])
def create_rule():
    form = RuleForm()
    if request.method == "GET":
        return render_template("create_rule.html", form=form)
    elif request.method == "POST":
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
        app.logger.info(request.form)
        rule = fsrm.load_rule(rule_id)
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
        return redirect(url_for("show_rule", rule_id=rule_id))


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
    return "OK"


@app.route("/ping", methods=["GET"])
@csrf.exempt
def ping():
    return "OK"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8888, debug=True)
