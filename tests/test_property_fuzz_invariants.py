import copy
import csv
import io
import random
import uuid
from collections import Counter

import pytest
from sqlalchemy.exc import IntegrityError

from ezrules.backend import data_utils
from ezrules.backend.data_utils import Event
from ezrules.backend.label_upload_service import LabelUploadService
from ezrules.core.field_paths import get_field_value, iter_field_paths, set_field_value
from ezrules.core.outcomes import DatabaseOutcome
from ezrules.core.rule import Rule
from ezrules.core.rule_engine import RuleEngine
from ezrules.core.type_casting import FieldCastConfig, FieldType, normalize_event
from ezrules.models.backend_core import AllowedOutcome, Organisation
from tests.canonical_helpers import add_served_decision


def _rng() -> random.Random:
    return random.Random(20260708)


def _field_path(rng: random.Random, prefix: str, depth: int | None = None) -> str:
    path_depth = depth or rng.randint(1, 4)
    return ".".join(f"{prefix}_{index}_{rng.randint(0, 999)}" for index in range(path_depth))


def _csv_content(rows: list[list[str]]) -> str:
    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerows(rows)
    return stream.getvalue()


def test_field_paths_round_trip_generated_nested_paths():
    rng = _rng()

    for index in range(100):
        field_path = _field_path(rng, f"field_{index}")
        expected_value = {
            "case": index,
            "amount": rng.randint(-10_000, 10_000),
            "flag": rng.choice([True, False]),
        }
        target: dict[str, object] = {}

        set_field_value(target, field_path, expected_value)

        assert get_field_value(target, field_path) == expected_value
        flattened = dict(iter_field_paths(target))
        assert flattened[field_path] == expected_value


def test_normalize_event_casts_generated_configured_leaves_without_mutating_source():
    rng = _rng()

    for index in range(60):
        int_path = _field_path(rng, f"integer_{index}", depth=3)
        float_path = _field_path(rng, f"float_{index}", depth=3)
        bool_path = _field_path(rng, f"boolean_{index}", depth=3)
        untouched_path = _field_path(rng, f"raw_{index}", depth=3)
        integer_value = rng.randint(-100_000, 100_000)
        float_value = round(rng.uniform(-10_000, 10_000), 4)
        bool_token, expected_bool = rng.choice(
            [
                ("true", True),
                ("TRUE", True),
                ("yes", True),
                ("1", True),
                ("false", False),
                ("FALSE", False),
                ("no", False),
                ("0", False),
            ]
        )
        event: dict[str, object] = {}
        set_field_value(event, int_path, str(integer_value))
        set_field_value(event, float_path, str(float_value))
        set_field_value(event, bool_path, bool_token)
        set_field_value(event, untouched_path, {"nested": [index, "kept"]})
        original = copy.deepcopy(event)

        normalized = normalize_event(
            event,
            [
                FieldCastConfig(field_name=int_path, field_type=FieldType.INTEGER, required=True),
                FieldCastConfig(field_name=float_path, field_type=FieldType.FLOAT),
                FieldCastConfig(field_name=bool_path, field_type=FieldType.BOOLEAN),
            ],
        )

        assert event == original
        assert get_field_value(normalized, int_path) == integer_value
        assert get_field_value(normalized, float_path) == pytest.approx(float_value)
        assert get_field_value(normalized, bool_path) is expected_bool
        assert get_field_value(normalized, untouched_path) == get_field_value(original, untouched_path)


def test_rule_parsing_and_execution_aggregate_generated_outcomes():
    rng = _rng()
    event: dict[str, object] = {}
    rules: list[Rule] = []
    expected_all_results: dict[int, str | None] = {}

    for index in range(50):
        field_path = _field_path(rng, f"metric_{index}", depth=2)
        observed_value = rng.randint(0, 200)
        threshold = rng.randint(0, 200)
        outcome = f"OUTCOME_{rng.randint(0, 6)}"
        set_field_value(event, field_path, observed_value)
        rule = Rule(
            rid=f"fuzz_rule_{index}",
            r_id=index + 1,
            logic=f"if ${field_path} >= {threshold}:\n\treturn !{outcome}\nreturn None",
        )

        rules.append(rule)
        expected_all_results[index + 1] = outcome if observed_value >= threshold else None
        assert rule.get_rule_params() == {field_path}

    result = RuleEngine(rules)(event)
    expected_rule_results = {
        rule_id: outcome for rule_id, outcome in expected_all_results.items() if outcome is not None
    }

    assert result["all_rule_results"] == expected_all_results
    assert result["rule_results"] == expected_rule_results
    assert result["outcome_counters"] == dict(Counter(expected_rule_results.values()))
    assert result["outcome_set"] == sorted(set(expected_rule_results.values()))


def test_csv_label_upload_parser_accounts_for_generated_rows():
    rng = _rng()
    rows: list[list[str]] = []
    expected_valid: list[tuple[int, str, int | None, str]] = []
    expected_error_count = 0

    for index in range(90):
        shape = rng.choice(["two_column", "three_column", "bad_width", "bad_version", "bad_empty"])
        transaction_id = f" txn_{index}_{rng.randint(0, 999)} "
        label_name = f" label_{rng.randint(0, 999)} "
        if shape == "two_column":
            rows.append([transaction_id, label_name])
            expected_valid.append((index + 1, transaction_id.strip(), None, label_name.strip().upper()))
        elif shape == "three_column":
            event_version = rng.randint(1, 50)
            rows.append([transaction_id, f" {event_version} ", label_name])
            expected_valid.append((index + 1, transaction_id.strip(), event_version, label_name.strip().upper()))
        elif shape == "bad_width":
            rows.append([transaction_id] if rng.choice([True, False]) else [transaction_id, "1", label_name, "extra"])
            expected_error_count += 1
        elif shape == "bad_version":
            rows.append([transaction_id, rng.choice(["not-int", "0", "-3"]), label_name])
            expected_error_count += 1
        else:
            rows.append([" ", label_name] if rng.choice([True, False]) else [transaction_id, " "])
            expected_error_count += 1

    parsed_rows, errors = LabelUploadService(None).parse_csv_content(_csv_content(rows))

    assert len(errors) == expected_error_count
    assert [
        (row.row_number, row.transaction_id, row.event_version, row.label_name) for row in parsed_rows
    ] == expected_valid


def test_find_duplicate_evaluation_matches_generated_equivalent_payloads(session):
    rng = _rng()
    org = session.query(Organisation).first()
    assert org is not None

    for index in range(12):
        transaction_id = f"fuzz_duplicate_{index}_{uuid.uuid4().hex[:8]}"
        effective_at = 1_710_000_000 + index
        event_data = {
            "amount": rng.randint(1, 10_000),
            "customer": {"id": f"cust_{rng.randint(1, 500)}", "risk": rng.choice(["low", "medium", "high"])},
        }
        decision = add_served_decision(
            session,
            org_id=int(org.o_id),
            transaction_id=transaction_id,
            effective_at=effective_at,
            event_data=copy.deepcopy(event_data),
            outcome_counters={"HOLD": 1},
            resolved_outcome="HOLD",
            rule_results={index + 1: "HOLD"},
        )

        duplicate = data_utils.find_duplicate_evaluation(
            session,
            int(org.o_id),
            Event(transaction_id=transaction_id, effective_at=effective_at, event_data=copy.deepcopy(event_data)),
        )
        changed_payload = data_utils.find_duplicate_evaluation(
            session,
            int(org.o_id),
            Event(
                transaction_id=transaction_id,
                effective_at=effective_at,
                event_data={**event_data, "amount": int(event_data["amount"]) + 1},
            ),
        )

        assert duplicate is not None
        assert duplicate["evaluation_id"] == int(decision.ed_id)
        assert duplicate["evaluation_status"] == "duplicate"
        assert duplicate["outcome_counters"] == {"HOLD": 1}
        assert changed_payload is None


def test_idempotency_keys_are_unique_per_org_and_reusable_across_orgs(session):
    org = session.query(Organisation).first()
    assert org is not None
    other_org = Organisation(name=f"fuzz_idempotency_{uuid.uuid4().hex[:8]}")
    session.add(other_org)
    session.flush()

    idempotency_key = f"idem_{uuid.uuid4().hex}"
    first = add_served_decision(
        session,
        org_id=int(org.o_id),
        transaction_id=f"idem_primary_{uuid.uuid4().hex[:8]}",
        effective_at=1_710_100_000,
        event_data={"amount": 10},
    )
    first.idempotency_key = idempotency_key
    same_key_other_org = add_served_decision(
        session,
        org_id=int(other_org.o_id),
        transaction_id=f"idem_other_{uuid.uuid4().hex[:8]}",
        effective_at=1_710_100_001,
        event_data={"amount": 20},
    )
    same_key_other_org.idempotency_key = idempotency_key
    session.flush()

    duplicate_same_org = add_served_decision(
        session,
        org_id=int(org.o_id),
        transaction_id=f"idem_duplicate_{uuid.uuid4().hex[:8]}",
        effective_at=1_710_100_002,
        event_data={"amount": 30},
    )
    duplicate_same_org.idempotency_key = idempotency_key

    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


def test_database_outcome_resolution_prefers_generated_severity_order_then_lexical_fallback(session):
    rng = _rng()
    org = Organisation(name=f"fuzz_outcome_{uuid.uuid4().hex[:8]}")
    session.add(org)
    session.flush()
    outcomes = [f"FUZZ_{index}_{rng.randint(100, 999)}" for index in range(8)]
    for severity_rank, outcome_name in enumerate(outcomes, start=1):
        session.add(AllowedOutcome(outcome_name=outcome_name, severity_rank=severity_rank, o_id=int(org.o_id)))
    session.flush()

    manager = DatabaseOutcome(session, int(org.o_id))

    assert manager.resolve_outcome({}) is None
    assert manager.resolve_outcome(None) is None

    for _ in range(40):
        selected_outcomes = rng.sample(outcomes, rng.randint(1, len(outcomes)))
        counters = {outcome: rng.randint(1, 5) for outcome in selected_outcomes}
        expected = min(selected_outcomes, key=outcomes.index)

        assert manager.resolve_outcome(counters) == expected

    unknown_counters = {"ZZ_UNKNOWN": 2, "AA_UNKNOWN": 1}

    assert manager.resolve_outcome(unknown_counters) == "AA_UNKNOWN"
