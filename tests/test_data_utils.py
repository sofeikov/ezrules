import pytest
from pydantic import ValidationError

from ezrules.backend.data_utils import Event


@pytest.mark.parametrize(
    "event_id, event_timestamp, event_data, expected",
    [
        ("evt1", 1609459200, {"key": "value"}, True),
        ("evt2", 0, {"key": "value"}, True),
        (
            "evt3",
            32503680000,
            {"key": "value"},
            True,
        ),
        ("evt4", -1, {"key": "value"}, False),
        (
            "evt5",
            32503680001,
            {"key": "value"},
            False,
        ),
        (
            "evt6",
            "1609459200",
            {"key": "value"},
            False,
        ),
        (
            "evt7",
            1609459200.5,
            {"key": "value"},
            False,
        ),
    ],
)
def test_event(event_id: str, event_timestamp: int, event_data: dict, expected: bool):
    if expected:
        # If expected is True, we expect the Event to be created successfully
        event = Event(event_id=event_id, event_timestamp=event_timestamp, event_data=event_data)
        assert event.event_id == event_id
        assert event.event_timestamp == event_timestamp
        assert event.event_data == event_data
    else:
        with pytest.raises(ValidationError):
            Event(
                event_id=event_id,
                event_timestamp=event_timestamp,
                event_data=event_data,
            )
