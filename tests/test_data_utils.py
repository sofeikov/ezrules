import pytest
from pydantic import ValidationError

from ezrules.backend.data_utils import Event


@pytest.mark.parametrize(
    "transaction_id, effective_at, event_data, expected",
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
def test_event(transaction_id: str, effective_at: int, event_data: dict, expected: bool):
    if expected:
        # If expected is True, we expect the Event to be created successfully
        event = Event(transaction_id=transaction_id, effective_at=effective_at, event_data=event_data)
        assert event.transaction_id == transaction_id
        assert event.effective_timestamp == effective_at
        assert event.event_data == event_data
    else:
        with pytest.raises(ValidationError):
            Event(
                transaction_id=transaction_id,
                effective_at=effective_at,
                event_data=event_data,
            )
