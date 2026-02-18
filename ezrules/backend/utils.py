import datetime
from typing import Any

from ezrules.core.type_casting import FieldCastConfig, FieldType
from ezrules.models.backend_core import FieldObservation, FieldTypeConfig


def conditional_decorator(condition, decorator):
    def wrapper(func):
        if condition:
            return decorator(func)
        return func

    return wrapper


def record_observations(db: Any, event_data: dict, o_id: int) -> None:
    """Upsert a FieldObservation row per (field, type) pair seen in event_data."""
    now = datetime.datetime.now(datetime.UTC)
    for field_name, value in event_data.items():
        observed_type = type(value).__name__
        existing = (
            db.query(FieldObservation)
            .filter(
                FieldObservation.field_name == field_name,
                FieldObservation.observed_json_type == observed_type,
                FieldObservation.o_id == o_id,
            )
            .first()
        )
        if existing:
            existing.last_seen = now
            existing.occurrence_count = (existing.occurrence_count or 0) + 1
        else:
            db.add(
                FieldObservation(
                    field_name=field_name,
                    observed_json_type=observed_type,
                    last_seen=now,
                    occurrence_count=1,
                    o_id=o_id,
                )
            )
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
