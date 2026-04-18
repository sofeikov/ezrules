from typing import Any

from sqlalchemy.dialects.postgresql import insert

from ezrules.backend.cast_config_cache import load_cast_configs as load_cached_cast_configs
from ezrules.core.field_paths import iter_field_paths
from ezrules.models.backend_core import FieldObservation


def conditional_decorator(condition, decorator):
    def wrapper(func):
        if condition:
            return decorator(func)
        return func

    return wrapper


def build_observation_rows(event_data: dict, o_id: int) -> list[dict[str, Any]]:
    observation_keys = {(o_id, field_name, type(value).__name__) for field_name, value in iter_field_paths(event_data)}
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


def load_cast_configs(db: Any, o_id: int):
    return load_cached_cast_configs(db, o_id)
