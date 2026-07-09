import string

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from ezrules.backend.features import extract_rule_stat_paths
from ezrules.core.rule import Rule

pytestmark = pytest.mark.property

PROPERTY_TEST_SETTINGS = settings(
    max_examples=75,
    derandomize=True,
    database=None,
)

_IDENTIFIER_START = tuple(string.ascii_letters + "_")
_IDENTIFIER_BODY = tuple(string.ascii_letters + string.digits + "_")


def _identifier_strategy() -> st.SearchStrategy[str]:
    return st.builds(
        lambda start, rest: start + rest,
        st.sampled_from(_IDENTIFIER_START),
        st.text(alphabet=_IDENTIFIER_BODY, min_size=0, max_size=8),
    )


FIELD_PATH_STRATEGY = st.lists(_identifier_strategy(), min_size=1, max_size=4).map(".".join)
STAT_PATH_STRATEGY = st.tuples(_identifier_strategy(), _identifier_strategy()).map(".".join)


@PROPERTY_TEST_SETTINGS
@given(field_path=FIELD_PATH_STRATEGY, quote=st.sampled_from(("'", '"')))
def test_rule_params_ignore_field_references_inside_string_literals(field_path: str, quote: str):
    rule = Rule(rid="property-string", logic=f"message = {quote}${field_path}{quote}\nreturn None")

    assert rule.get_rule_params() == set()


@PROPERTY_TEST_SETTINGS
@given(field_path=FIELD_PATH_STRATEGY)
def test_rule_params_ignore_field_references_inside_comments(field_path: str):
    rule = Rule(rid="property-comment", logic=f"# ${field_path}\nreturn None")

    assert rule.get_rule_params() == set()


@PROPERTY_TEST_SETTINGS
@given(field_paths=st.lists(FIELD_PATH_STRATEGY, min_size=1, max_size=5))
def test_rule_params_extract_each_generated_field_path_once(field_paths: list[str]):
    repeated_field_paths = field_paths + list(reversed(field_paths))
    conditions = " and ".join(f"${field_path} is not None" for field_path in repeated_field_paths)
    rule = Rule(rid="property-live-fields", logic=f"if {conditions}:\n\treturn !HOLD\nreturn None")

    assert rule.get_rule_params() == set(repeated_field_paths)


@PROPERTY_TEST_SETTINGS
@given(
    field_paths=st.lists(FIELD_PATH_STRATEGY, min_size=1, max_size=4),
    stat_paths=st.lists(STAT_PATH_STRATEGY, min_size=1, max_size=4),
)
def test_rule_params_and_stats_keep_live_fields_separate(field_paths: list[str], stat_paths: list[str]):
    field_checks = [f"${field_path} is not None" for field_path in field_paths]
    stat_checks = [f"stat[{stat_path}] >= 0" for stat_path in stat_paths]
    checks = " and ".join(field_checks + stat_checks)
    rule = Rule(rid="property-live-mixed", logic=f"if {checks}:\n\treturn !HOLD\nreturn None")

    assert rule.get_rule_params() == set(field_paths)
    assert rule.get_rule_stats() == set(stat_paths)


@PROPERTY_TEST_SETTINGS
@given(hidden_stat_path=STAT_PATH_STRATEGY, stat_paths=st.lists(STAT_PATH_STRATEGY, min_size=1, max_size=4))
def test_stat_reference_extraction_ignores_hidden_tokens_and_deduplicates_live_paths(
    hidden_stat_path: str, stat_paths: list[str]
):
    assume(hidden_stat_path not in stat_paths)
    repeated_stat_paths = stat_paths + stat_paths[:2]
    live_checks = " and ".join(f"stat[{stat_path}] >= 0" for stat_path in repeated_stat_paths)
    logic = (
        f'message = "stat[{hidden_stat_path}]"\n'
        f"# stat[{hidden_stat_path}]\n"
        f"if {live_checks}:\n\treturn !HOLD\n"
        "return None"
    )

    assert extract_rule_stat_paths(logic) == list(dict.fromkeys(repeated_stat_paths))
    assert Rule(rid="property-hidden-stats", logic=logic).get_rule_stats() == set(repeated_stat_paths)
