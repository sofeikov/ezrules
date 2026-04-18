from ezrules.backend.api_v2.routes.tested_events import list_tested_events
from ezrules.models.backend_core import Rule
from tests.test_api_v2_tested_events_rule_fields import (
    _save_rule_config,
    _store_event,
    tested_events_field_client,
)


def test_tested_events_returns_nested_referenced_fields(session, tested_events_field_client):
    org = tested_events_field_client.test_data["org"]

    session.add(
        Rule(
            logic="if $customer.profile.age >= 21:\n\treturn !HOLD",
            description="Hold adult profiles",
            rid="EVENTS:NESTED:001",
            o_id=org.o_id,
            r_id=9301,
        )
    )
    session.commit()
    _save_rule_config(session, org.o_id)

    _store_event(
        session,
        org.o_id,
        "evt-nested-fields",
        1700000300,
        {"customer": {"profile": {"age": 34}, "country": "GB"}},
    )

    payload = list_tested_events(
        limit=50,
        include_referenced_fields=True,
        user=None,
        _=None,
        current_org_id=int(org.o_id),
        db=session,
    )

    assert payload.events[0].event_id == "evt-nested-fields"
    assert payload.events[0].event_data == {"customer": {"profile": {"age": 34}, "country": "GB"}}
    assert [item.model_dump(exclude_unset=True) for item in payload.events[0].triggered_rules] == [
        {
            "r_id": 9301,
            "rid": "EVENTS:NESTED:001",
            "description": "Hold adult profiles",
            "outcome": "HOLD",
            "referenced_fields": ["customer.profile.age"],
        }
    ]
