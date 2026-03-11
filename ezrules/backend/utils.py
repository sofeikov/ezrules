import datetime
from typing import Any

from sqlalchemy import tuple_

from ezrules.core.type_casting import FieldCastConfig, FieldType
from ezrules.models.backend_core import FieldObservation, FieldTypeConfig


def conditional_decorator(condition, decorator):
    def wrapper(func):
        if condition:
            return decorator(func)
        return func

    return wrapper


def record_observations(db: Any, event_data: dict, o_id: int, commit: bool = True) -> None:
    """Upsert a FieldObservation row per (field, type) pair seen in event_data."""
    if not event_data:
        return

    if not commit:
        db.flush()

    now = datetime.datetime.now(datetime.UTC)
    field_pairs = [(field_name, type(value).__name__) for field_name, value in event_data.items()]
    existing_rows = (
        db.query(FieldObservation)
        .filter(
            FieldObservation.o_id == o_id,
            tuple_(FieldObservation.field_name, FieldObservation.observed_json_type).in_(field_pairs),
        )
        .all()
    )
    existing_map = {(row.field_name, row.observed_json_type): row for row in existing_rows}

    for field_name, value in event_data.items():
        observed_type = type(value).__name__
        existing = existing_map.get((field_name, observed_type))
        if existing:
            existing.last_seen = now
            existing.occurrence_count = (existing.occurrence_count or 0) + 1
        else:
            observation = FieldObservation(
                field_name=field_name,
                observed_json_type=observed_type,
                last_seen=now,
                occurrence_count=1,
                o_id=o_id,
            )
            db.add(observation)
            existing_map[(field_name, observed_type)] = observation
    if commit:
        db.commit()


def load_cast_configs(db: Any, o_id: int) -> list[FieldCastConfig]:
    """Load FieldTypeConfig rows for an org and return as FieldCastConfig objects."""
    rows = db.query(FieldTypeConfig).filter(FieldTypeConfig.o_id == o_id).all()
    return [
        FieldCastConfig(
            field_name=row.field_name,
            field_type=FieldType(row.configured_type),
            datetime_format=row.datetime_format,
        )
        for row in rows
    ]
