import importlib

from ezrules.demo_data import build_demo_events, build_demo_rules

bombard = importlib.import_module("scripts.bombard_evaluator")


def test_build_demo_events_include_nested_customer_and_sender_payloads():
    event = build_demo_events(1)[0].event_data

    assert event["customer"] == {
        "id": event["customer_id"],
        "country": event["customer_country"],
        "profile": {
            "age": event["customer"]["profile"]["age"],
            "segment": event["customer"]["profile"]["segment"],
        },
        "account": {
            "age_days": event["account_age_days"],
            "email_age_days": event["email_age_days"],
            "prior_chargebacks_180d": event["prior_chargebacks_180d"],
        },
        "behavior": {
            "avg_amount_30d": event["customer_avg_amount_30d"],
            "std_amount_30d": event["customer_std_amount_30d"],
        },
    }
    assert event["sender"] == {
        "id": event["customer_id"],
        "country": event["billing_country"],
        "account": {
            "age_days": event["account_age_days"],
        },
        "origin": {
            "country": event["ip_country"],
        },
        "device": {
            "age_days": event["device_age_days"],
            "trust_score": event["device_trust_score"],
        },
    }


def test_first_demo_rule_batch_includes_nested_showcase_rule():
    rules = build_demo_rules(10)

    nested_rules = [
        rule for rule in rules if "$customer.profile.age" in rule.logic and "$sender.origin.country" in rule.logic
    ]

    assert len(nested_rules) == 1
    assert "nested-path rule" in nested_rules[0].description


def test_bombard_events_reuse_nested_demo_payload_shape():
    events = bombard.build_bombard_events(2, start_index=10)

    assert events[0]["event_data"]["customer"]["account"]["age_days"] == events[0]["event_data"]["account_age_days"]
    assert events[0]["event_data"]["sender"]["origin"]["country"] == events[0]["event_data"]["ip_country"]
    assert "send_country" not in events[0]["event_data"]
