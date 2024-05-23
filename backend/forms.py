from wtforms import StringField, SubmitField, Field, TextAreaField
from wtforms.widgets import TextInput
from flask_wtf import FlaskForm
from core.rule import RuleFactory
from collections import namedtuple


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
