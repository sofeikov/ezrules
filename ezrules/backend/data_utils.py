from pydantic import BaseModel, field_validator

from ezrules.models.backend_core import TestingRecordLog, TestingResultsLog


class Event(BaseModel):
    event_id: str
    event_timestamp: int  # Assuming Unix timestamp as input
    event_data: dict

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


def eval_and_store(lre, event: Event):
    db_session = lre.db
    tl = TestingRecordLog(
        o_id=lre.o_id,
        event=event.event_data,
        event_timestamp=event.event_timestamp,
        event_id=event.event_id,
    )
    db_session.add(tl)
    db_session.commit()
    response = lre.evaluate_rules(event.event_data)
    for r_id, result in response["rule_results"].items():
        trl = TestingResultsLog(tl_id=tl.tl_id, r_id=r_id, rule_result=result)
        db_session.add(trl)
    db_session.commit()
    return response
