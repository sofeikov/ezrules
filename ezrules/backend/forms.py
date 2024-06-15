from collections import namedtuple

from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, TextAreaField

from ezrules.core.rule import RuleFactory

RuleStatusCheck = namedtuple("RuleStatusCheck", ["rule_ok", "reasons"])


class RuleForm(FlaskForm):
    rid = StringField("A Unique rule ID")
    description = StringField("Rule description")
    logic = TextAreaField("Rule logic")
    submit = SubmitField("Submit")

    def validate(self, rule_checker=None, extra_validators=None) -> RuleStatusCheck:
        base_validation = super().validate(extra_validators)
        rule_ok = True
        reasons = []
        if rule_checker:
            rule_raw_config = self.data
            rule = RuleFactory.from_json(rule_raw_config)
            rule_ok, reasons = rule_checker.is_rule_valid(rule)
        rule_is_fully_ok = rule_ok and base_validation
        return RuleStatusCheck(rule_is_fully_ok, reasons)


class OutcomeForm(FlaskForm):
    outcome = StringField("Outcome name(e.g. CANCEL)")
    submit = SubmitField("Add")
