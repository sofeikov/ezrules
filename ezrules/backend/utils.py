from typing import Any

from sqlalchemy.dialects.postgresql import insert

from ezrules.core.type_casting import FieldCastConfig, FieldType
from ezrules.models.backend_core import FieldObservation, FieldTypeConfig


def conditional_decorator(condition, decorator):
    def wrapper(func):
        if condition:
            return decorator(func)
        return func

    return wrapper


def build_observation_rows(event_data: dict, o_id: int) -> list[dict[str, Any]]:
    observation_keys = {(o_id, field_name, type(value).__name__) for field_name, value in event_data.items()}
    return [
        {
            "o_id": current_o_id,
            "field_name": field_name,
            "observed_json_type": observed_json_type,
        }
        for current_o_id, field_name, observed_json_type in observation_keys
    ]


def upsert_field_observations(db: Any, observation_rows: list[dict[str, Any]], *, commit: bool = True) -> None:
    if not observation_rows:
        return

    statement = insert(FieldObservation).values(observation_rows)
    statement = statement.on_conflict_do_nothing(
        index_elements=[
            FieldObservation.field_name,
            FieldObservation.observed_json_type,
            FieldObservation.o_id,
        ]
    )
    db.execute(statement)
    if commit:
        db.commit()
    else:
        db.flush()


def record_observations(db: Any, event_data: dict, o_id: int, commit: bool = True) -> None:
    """Insert one FieldObservation row per distinct (field, type) pair seen in event_data."""
    if not event_data:
        return

    upsert_field_observations(
        db,
        build_observation_rows(event_data, o_id),
        commit=commit,
    )


def load_cast_configs(db: Any, o_id: int) -> list[FieldCastConfig]:
    """Load FieldTypeConfig rows for an org and return as FieldCastConfig objects."""
    rows = db.query(FieldTypeConfig).filter(FieldTypeConfig.o_id == o_id).all()
    return [
        FieldCastConfig(
            field_name=row.field_name,
            field_type=FieldType(row.configured_type),
            datetime_format=row.datetime_format,
            required=bool(row.required),
        )
        for row in rows
    ]
