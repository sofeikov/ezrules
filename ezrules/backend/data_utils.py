from typing import Dict

from pydantic import BaseModel, field_validator


class Event(BaseModel):
    event_id: str
    event_timestamp: int  # Assuming Unix timestamp as input
    event_data: Dict

    @field_validator("event_timestamp", mode="before")
    def validate_unix_timestamp(cls, value):
        # Ensure the timestamp is an integer
        if not isinstance(value, int):
            raise ValueError("Timestamp must be an integer")

        # Ensure the timestamp is in a reasonable range (e.g., 1970-01-01 to 3000-01-01)
        min_timestamp = 0  # Unix timestamp for 1970-01-01T00:00:00Z
        max_timestamp = (
            32503680000  # Approximate Unix timestamp for 3000-01-01T00:00:00Z
        )
        if not (min_timestamp <= value <= max_timestamp):
            raise ValueError("Timestamp out of range")

        return value
