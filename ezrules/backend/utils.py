from typing import Any

from ezrules.core.type_casting import FieldCastConfig, FieldType
from ezrules.models.backend_core import FieldTypeConfig


def conditional_decorator(condition, decorator):
    def wrapper(func):
        if condition:
            return decorator(func)
        return func

    return wrapper


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
