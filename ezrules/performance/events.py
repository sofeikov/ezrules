from __future__ import annotations

import random
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

type EventPayload = dict[str, Any]


def build_evaluate_payload(
    *,
    transaction_id: str,
    match_profile: str,
    seed: int,
) -> dict[str, Any]:
    """Build a deterministic evaluator request for one matrix row."""

    event_data = build_event_data(match_profile=match_profile, seed=seed)
    return {
        "transaction_id": transaction_id,
        "effective_at": int(datetime.now(UTC).timestamp()),
        "event_data": event_data,
    }


def build_event_data(*, match_profile: str, seed: int) -> EventPayload:
    """Build deterministic demo-compatible event data for the requested profile."""

    rng = random.Random(seed)
    normalized_profile = match_profile.strip().lower()
    if normalized_profile in {"none", "no_match", "low_risk"}:
        return _with_nested_entities(_low_risk_payload(rng))
    if normalized_profile in {"many_matches", "high_risk", "stress"}:
        return _with_nested_entities(_high_risk_payload(rng))
    if normalized_profile in {"early_match", "cross_border"}:
        return _with_nested_entities(_cross_border_payload(rng))
    if normalized_profile in {"late_match", "payout"}:
        return _with_nested_entities(_payout_payload(rng))
    if normalized_profile in {"mixed", "realistic"}:
        return _with_nested_entities(
            rng.choice(
                [
                    _low_risk_payload,
                    _cross_border_payload,
                    _high_risk_payload,
                    _payout_payload,
                ]
            )(rng)
        )
    raise ValueError(f"Unknown match profile: {match_profile}")


def _base_payload(rng: random.Random) -> EventPayload:
    customer_id = f"perf_cust_{rng.randint(1, 50_000):05d}"
    return {
        "amount": round(rng.uniform(35, 180), 2),
        "currency": "USD",
        "txn_type": "card_purchase",
        "channel": "web",
        "customer_id": customer_id,
        "customer_country": "US",
        "billing_country": "US",
        "shipping_country": "US",
        "ip_country": "US",
        "merchant_id": "mrc_dailycart",
        "merchant_category": "groceries",
        "merchant_country": "US",
        "email_domain": "gmail.com",
        "account_age_days": 840,
        "email_age_days": 780,
        "customer_avg_amount_30d": 120.0,
        "customer_std_amount_30d": 35.0,
        "prior_chargebacks_180d": 0,
        "manual_review_hits_30d": 0,
        "decline_count_24h": 0,
        "txn_velocity_10m": 1,
        "txn_velocity_1h": 1,
        "unique_cards_24h": 1,
        "device_age_days": 365,
        "device_trust_score": 94,
        "has_3ds": 1,
        "card_present": 0,
        "is_guest_checkout": 0,
        "password_reset_age_hours": 480,
        "distance_from_home_km": 20,
        "ip_proxy_score": 5,
        "beneficiary_country": "US",
        "beneficiary_age_days": 365,
        "local_hour": 14,
    }


def _low_risk_payload(rng: random.Random) -> EventPayload:
    payload = _base_payload(rng)
    payload["amount"] = round(rng.uniform(25, 95), 2)
    return payload


def _cross_border_payload(rng: random.Random) -> EventPayload:
    payload = _base_payload(rng)
    payload.update(
        {
            "amount": round(rng.uniform(850, 1800), 2),
            "shipping_country": "BR",
            "ip_country": "AE",
            "merchant_category": "electronics",
            "merchant_id": "mrc_gadgethub",
            "account_age_days": 12,
            "email_age_days": 8,
            "device_age_days": 1,
            "device_trust_score": 24,
            "has_3ds": 0,
            "is_guest_checkout": 1,
            "txn_velocity_10m": 4,
            "txn_velocity_1h": 6,
            "unique_cards_24h": 2,
            "distance_from_home_km": 5200,
            "local_hour": 2,
        }
    )
    return payload


def _high_risk_payload(rng: random.Random) -> EventPayload:
    payload = _cross_border_payload(rng)
    payload.update(
        {
            "amount": round(rng.uniform(1800, 4200), 2),
            "merchant_category": "gift_cards",
            "merchant_id": "mrc_cardhub",
            "email_domain": "mailinator.com",
            "customer_avg_amount_30d": 110.0,
            "customer_std_amount_30d": 28.0,
            "prior_chargebacks_180d": 3,
            "manual_review_hits_30d": 3,
            "decline_count_24h": 9,
            "txn_velocity_10m": 12,
            "txn_velocity_1h": 24,
            "unique_cards_24h": 6,
            "ip_proxy_score": 91,
            "password_reset_age_hours": 2,
        }
    )
    return payload


def _payout_payload(rng: random.Random) -> EventPayload:
    payload = _high_risk_payload(rng)
    payload.update(
        {
            "txn_type": "wallet_cashout",
            "merchant_category": "crypto",
            "merchant_id": "mrc_coinlane",
            "beneficiary_country": "IR",
            "beneficiary_age_days": 1,
            "amount": round(rng.uniform(900, 3000), 2),
        }
    )
    return payload


def _with_nested_entities(payload: EventPayload) -> EventPayload:
    event_data = deepcopy(payload)
    event_data["customer"] = {
        "id": event_data["customer_id"],
        "country": event_data["customer_country"],
        "profile": {"age": 37, "segment": "established"},
        "account": {
            "age_days": event_data["account_age_days"],
            "email_age_days": event_data["email_age_days"],
            "prior_chargebacks_180d": event_data["prior_chargebacks_180d"],
        },
        "behavior": {
            "avg_amount_30d": event_data["customer_avg_amount_30d"],
            "std_amount_30d": event_data["customer_std_amount_30d"],
        },
    }
    event_data["sender"] = {
        "id": event_data["customer_id"],
        "country": event_data["billing_country"],
        "account": {"age_days": event_data["account_age_days"]},
        "origin": {"country": event_data["ip_country"]},
        "device": {
            "age_days": event_data["device_age_days"],
            "trust_score": event_data["device_trust_score"],
        },
    }
    return event_data
