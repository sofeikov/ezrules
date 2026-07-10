from __future__ import annotations

import hashlib
import math
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import pytest

from ezrules.backend.features import compute_feature
from ezrules.models.backend_core import EventVersion, FeatureDefinition, Organisation
from tests.canonical_helpers import _hash_payload
from tests.feature_math_oracle import aggregate_numeric, count_distinct, days_since_first_seen

AS_OF = datetime(2026, 7, 1, 12, 0, tzinfo=UTC)
WINDOW_SECONDS = 604800


def _add_event(
    session,
    *,
    org_id: int,
    transaction_id: str,
    effective_at: datetime,
    event_data: dict[str, Any],
    observed_at: datetime | None = None,
) -> EventVersion:
    latest = (
        session.query(EventVersion)
        .filter(EventVersion.o_id == org_id, EventVersion.transaction_id == transaction_id)
        .order_by(EventVersion.event_version.desc(), EventVersion.ev_id.desc())
        .first()
    )
    event = EventVersion(
        o_id=org_id,
        transaction_id=transaction_id,
        event_version=1 if latest is None else int(latest.event_version) + 1,
        effective_at=effective_at,
        observed_at=observed_at or effective_at,
        event_data=event_data,
        payload_hash=_hash_payload(event_data),
        supersedes_ev_id=None if latest is None else int(latest.ev_id),
        terminal_state=False,
    )
    session.add(event)
    session.flush()
    return event


def _feature(
    org_id: int,
    aggregation: str,
    *,
    source_field: str | None = "amount",
    window_seconds: int = WINDOW_SECONDS,
    filters: list[dict[str, Any]] | None = None,
    null_handling: str = "exclude",
) -> FeatureDefinition:
    return FeatureDefinition(
        o_id=org_id,
        name=f"Contract {aggregation}",
        entity="sender",
        feature_name=f"contract_{aggregation}",
        feature_kind="aggregate",
        entity_key="sender_id",
        aggregation_type=aggregation,
        source_field=source_field,
        window_seconds=window_seconds,
        filters=filters or [],
        null_handling=null_handling,
        status="active",
    )


@pytest.fixture
def org_id(session) -> int:
    return int(session.query(Organisation).one().o_id)


@pytest.fixture
def canonical_events(session, org_id):
    values = ["10", "20", "20", "40"]
    effective_times = [AS_OF - timedelta(days=3, hours=index) for index in range(len(values))]
    for index, (value, effective_at) in enumerate(zip(values, effective_times, strict=True)):
        _add_event(
            session,
            org_id=org_id,
            transaction_id=f"aggregate-contract-{index}",
            effective_at=effective_at,
            event_data={"sender_id": "S1", "amount": value},
        )
    session.commit()
    return values, effective_times


@pytest.mark.parametrize(
    "aggregation",
    ["count", "count_distinct", "sum", "avg", "min", "max", "stddev", "days_since_first_seen"],
)
def test_every_aggregate_matches_independent_oracle(session, org_id, canonical_events, aggregation):
    values, effective_times = canonical_events
    source_field = None if aggregation in {"count", "days_since_first_seen"} else "amount"
    feature = _feature(org_id, aggregation, source_field=source_field)

    result = compute_feature(session, org_id, feature, {"sender_id": "S1"}, AS_OF)

    if aggregation == "count":
        expected: Decimal | int | None = len(values)
    elif aggregation == "count_distinct":
        expected = count_distinct(values)
    elif aggregation == "days_since_first_seen":
        expected = days_since_first_seen(AS_OF, effective_times)
    else:
        expected = aggregate_numeric(aggregation, values)

    assert result.matched_event_count == 4
    if isinstance(expected, Decimal):
        assert Decimal(str(result.value)) == pytest.approx(expected)
    else:
        assert result.value == expected


def test_window_and_observation_boundaries_are_exact(session, org_id):
    window_seconds = 3600
    window_start = AS_OF - timedelta(seconds=window_seconds)
    cases = [
        ("at-window-start", window_start, window_start, "10", "S1", "approved"),
        (
            "inside-window",
            window_start + timedelta(seconds=1),
            window_start + timedelta(seconds=1),
            "20",
            "S1",
            "approved",
        ),
        ("at-as-of", AS_OF, AS_OF, "1000", "S1", "approved"),
        ("before-window", window_start - timedelta(microseconds=1), window_start, "2000", "S1", "approved"),
        (
            "observed-late",
            window_start + timedelta(minutes=10),
            AS_OF + timedelta(microseconds=1),
            "3000",
            "S1",
            "approved",
        ),
        ("other-entity", window_start + timedelta(minutes=20), window_start, "4000", "S2", "approved"),
        ("filter-mismatch", window_start + timedelta(minutes=30), window_start, "5000", "S1", "declined"),
    ]
    for transaction_id, effective_at, observed_at, amount, sender_id, status in cases:
        _add_event(
            session,
            org_id=org_id,
            transaction_id=transaction_id,
            effective_at=effective_at,
            observed_at=observed_at,
            event_data={"sender_id": sender_id, "amount": amount, "status": status},
        )
    session.commit()
    feature = _feature(
        org_id,
        "sum",
        window_seconds=window_seconds,
        filters=[{"field": "status", "operator": "in", "value": ["approved"]}],
    )

    result = compute_feature(session, org_id, feature, {"sender_id": "S1"}, AS_OF)

    expected = aggregate_numeric("sum", ["10", "20"])
    assert result.window_start == window_start
    assert result.matched_event_count == 2
    assert Decimal(str(result.value)) == expected


@pytest.mark.parametrize(
    ("null_handling", "expected"),
    [
        ("exclude", Decimal("10")),
        ("zero", Decimal("10")),
    ],
)
def test_numeric_aggregates_exclude_invalid_and_non_finite_values(session, org_id, null_handling, expected):
    values = ["10", None, "missing", "NaN", "Infinity", True]
    for index, value in enumerate(values):
        event_data = {"sender_id": "S1"}
        if value != "missing":
            event_data["amount"] = value
        _add_event(
            session,
            org_id=org_id,
            transaction_id=f"numeric-input-{null_handling}-{index}",
            effective_at=AS_OF - timedelta(minutes=index + 1),
            event_data=event_data,
        )
    session.commit()
    feature = _feature(org_id, "sum", null_handling=null_handling)

    result = compute_feature(session, org_id, feature, {"sender_id": "S1"}, AS_OF)

    oracle = aggregate_numeric("sum", ["10", None, None, "NaN", "Infinity", True], null_handling=null_handling)
    assert oracle == expected
    assert Decimal(str(result.value)) == oracle
    assert result.warning == "Excluded 3 invalid or non-finite numeric source value(s)"


def test_large_numeric_strings_follow_documented_float_tolerance(session, org_id):
    values = ["9007199254740993", "0.1", "0.2"]
    for index, value in enumerate(values):
        _add_event(
            session,
            org_id=org_id,
            transaction_id=f"large-number-{index}",
            effective_at=AS_OF - timedelta(minutes=index + 1),
            event_data={"sender_id": "S1", "amount": value},
        )
    session.commit()
    feature = _feature(org_id, "sum")

    result = compute_feature(session, org_id, feature, {"sender_id": "S1"}, AS_OF)

    oracle = aggregate_numeric("sum", values)
    assert oracle is not None
    assert math.isclose(result.value, float(oracle), rel_tol=1e-15, abs_tol=0.0)


@pytest.mark.parametrize(
    ("aggregation", "values", "expected"),
    [
        ("sum", ["1e308", "1e308"], None),
        ("avg", ["1e308", "1e308"], 1e308),
        ("stddev", ["1e308", "-1e308"], 1e308),
    ],
)
def test_near_float_limit_results_are_finite_or_warned_null(session, org_id, aggregation, values, expected):
    for index, value in enumerate(values):
        _add_event(
            session,
            org_id=org_id,
            transaction_id=f"float-limit-{aggregation}-{index}",
            effective_at=AS_OF - timedelta(minutes=index + 1),
            event_data={"sender_id": "S1", "amount": value},
        )
    session.commit()

    result = compute_feature(session, org_id, _feature(org_id, aggregation), {"sender_id": "S1"}, AS_OF)

    if expected is None:
        assert result.value is None
        assert result.warning == "Aggregate result exceeded the finite binary floating-point range"
    else:
        assert math.isfinite(result.value)
        assert result.value == pytest.approx(expected)
        assert result.warning is None


def test_graph_result_preserves_persisted_textual_entity_hash(session, org_id):
    feature = FeatureDefinition(
        o_id=org_id,
        name="Graph hash compatibility",
        entity="sender",
        feature_name="graph_hash_compatibility",
        feature_kind="graph",
        entity_key="sender_id",
        aggregation_type="graph_distinct_count",
        source_field=None,
        window_seconds=WINDOW_SECONDS,
        filters=[],
        null_handling="exclude",
        graph_config={
            "target_entity": "device",
            "allowed_entity_types": ["sender", "device"],
            "max_depth": 1,
        },
        status="active",
    )

    result = compute_feature(session, org_id, feature, {"sender_id": "S1"}, AS_OF)

    assert result.value == 0
    assert result.entity_value_hash == hashlib.sha256(b"S1").hexdigest()


@pytest.mark.parametrize(
    ("null_handling", "expected"),
    [("exclude", 10.0), ("zero", 5.0)],
)
def test_null_policy_changes_numeric_denominator(session, org_id, null_handling, expected):
    for index, value in enumerate(("10", None)):
        _add_event(
            session,
            org_id=org_id,
            transaction_id=f"null-policy-{null_handling}-{index}",
            effective_at=AS_OF - timedelta(minutes=index + 1),
            event_data={"sender_id": "S1", "amount": value},
        )
    session.commit()

    result = compute_feature(
        session,
        org_id,
        _feature(org_id, "avg", null_handling=null_handling),
        {"sender_id": "S1"},
        AS_OF,
    )

    assert result.value == pytest.approx(expected)


def test_count_distinct_uses_typed_scalar_identity(session, org_id):
    values = [1, "1", 1.0, True, False, None, {"nested": 1}, [1]]
    for index, value in enumerate(values):
        _add_event(
            session,
            org_id=org_id,
            transaction_id=f"distinct-identity-{index}",
            effective_at=AS_OF - timedelta(minutes=index + 1),
            event_data={"sender_id": "S1", "value": value},
        )
    session.commit()

    result = compute_feature(
        session,
        org_id,
        _feature(org_id, "count_distinct", source_field="value"),
        {"sender_id": "S1"},
        AS_OF,
    )

    assert result.value == count_distinct(values) == 4


def test_entity_and_filter_comparisons_preserve_json_scalar_types(session, org_id):
    cases = [
        ("number-number", 1, 1, "10"),
        ("number-string", 1, "1", "100"),
        ("string-number", "1", 1, "1000"),
        ("string-string", "1", "1", "20"),
    ]
    for transaction_id, sender_id, segment, amount in cases:
        _add_event(
            session,
            org_id=org_id,
            transaction_id=transaction_id,
            effective_at=AS_OF - timedelta(minutes=1),
            event_data={"sender_id": sender_id, "segment": segment, "amount": amount},
        )
    session.commit()
    feature = _feature(
        org_id,
        "sum",
        filters=[{"field": "segment", "operator": "eq", "value": 1}],
    )

    number_result = compute_feature(session, org_id, feature, {"sender_id": 1}, AS_OF)
    string_result = compute_feature(session, org_id, feature, {"sender_id": "1"}, AS_OF)

    assert number_result.value == 10
    assert string_result.value == 1000


def test_future_effective_version_does_not_replace_historical_version(session, org_id):
    _add_event(
        session,
        org_id=org_id,
        transaction_id="future-effective-correction",
        effective_at=AS_OF - timedelta(hours=1),
        observed_at=AS_OF - timedelta(hours=1),
        event_data={"sender_id": "S1", "amount": "10"},
    )
    _add_event(
        session,
        org_id=org_id,
        transaction_id="future-effective-correction",
        effective_at=AS_OF + timedelta(hours=1),
        observed_at=AS_OF - timedelta(minutes=1),
        event_data={"sender_id": "S1", "amount": "1000"},
    )
    session.commit()

    result = compute_feature(session, org_id, _feature(org_id, "sum"), {"sender_id": "S1"}, AS_OF)

    assert result.value == 10
    assert result.matched_event_count == 1


def test_latest_observed_correction_replaces_prior_version(session, org_id):
    effective_at = AS_OF - timedelta(hours=1)
    _add_event(
        session,
        org_id=org_id,
        transaction_id="corrected-transaction",
        effective_at=effective_at,
        observed_at=AS_OF - timedelta(minutes=30),
        event_data={"sender_id": "S1", "amount": "100"},
    )
    _add_event(
        session,
        org_id=org_id,
        transaction_id="corrected-transaction",
        effective_at=effective_at,
        observed_at=AS_OF - timedelta(minutes=10),
        event_data={"sender_id": "S1", "amount": "10"},
    )
    session.commit()
    feature = _feature(org_id, "sum")

    before = compute_feature(session, org_id, feature, {"sender_id": "S1"}, AS_OF - timedelta(minutes=20))
    after = compute_feature(session, org_id, feature, {"sender_id": "S1"}, AS_OF)

    assert before.value == 100
    assert after.value == 10
    assert before.matched_event_count == after.matched_event_count == 1


def test_as_of_timezone_representation_does_not_change_result(session, org_id):
    _add_event(
        session,
        org_id=org_id,
        transaction_id="timezone-equivalence",
        effective_at=AS_OF - timedelta(minutes=5),
        event_data={"sender_id": "S1", "amount": "12.5"},
    )
    session.commit()
    feature = _feature(org_id, "sum")

    utc_result = compute_feature(session, org_id, feature, {"sender_id": "S1"}, AS_OF)
    offset_result = compute_feature(
        session,
        org_id,
        feature,
        {"sender_id": "S1"},
        AS_OF.astimezone(timezone(timedelta(hours=5, minutes=30))),
    )

    assert utc_result == offset_result
