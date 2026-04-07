import logging
from dataclasses import dataclass
from functools import lru_cache
from threading import Lock
from typing import Any

from redis import Redis

from ezrules.core.type_casting import FieldCastConfig, FieldType
from ezrules.models.backend_core import FieldTypeConfig
from ezrules.settings import app_settings

logger = logging.getLogger(__name__)

_CAST_CONFIG_VERSION_KEY_PREFIX = "ezrules:field_type_config_version"


def _cast_config_cache_url() -> str:
    return app_settings.OBSERVATION_QUEUE_REDIS_URL or app_settings.CELERY_BROKER_URL


@lru_cache(maxsize=1)
def get_cast_config_cache_client() -> Redis:
    return Redis.from_url(_cast_config_cache_url(), decode_responses=True)


def _load_cast_configs_from_db(db: Any, o_id: int) -> list[FieldCastConfig]:
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


def _version_key(o_id: int) -> str:
    return f"{_CAST_CONFIG_VERSION_KEY_PREFIX}:{o_id}"


@dataclass(frozen=True)
class _CacheEntry:
    version: str
    configs: list[FieldCastConfig]


class CastConfigCache:
    def __init__(self, client_getter=None):
        self._client_getter = client_getter or get_cast_config_cache_client
        self._entries: dict[int, _CacheEntry] = {}
        self._lock = Lock()

    def load(self, db: Any, o_id: int) -> list[FieldCastConfig]:
        version = self._read_version(o_id)
        if version is None:
            self.invalidate_local(o_id)
            return _load_cast_configs_from_db(db, o_id)

        with self._lock:
            entry = self._entries.get(o_id)
            if entry is not None and entry.version == version:
                return entry.configs

        configs = _load_cast_configs_from_db(db, o_id)

        with self._lock:
            self._entries[o_id] = _CacheEntry(version=version, configs=configs)

        return configs

    def invalidate(self, o_id: int) -> bool:
        self.invalidate_local(o_id)

        client = self._get_client()
        if client is None:
            return False

        try:
            client.incr(_version_key(o_id))
        except Exception:
            logger.exception("Failed to invalidate cast config cache for org_id=%s", o_id)
            return False

        return True

    def invalidate_local(self, o_id: int) -> None:
        with self._lock:
            self._entries.pop(o_id, None)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    def _get_client(self) -> Redis | None:
        try:
            return self._client_getter()
        except Exception:
            logger.exception("Failed to create cast config cache Redis client")
            return None

    def _read_version(self, o_id: int) -> str | None:
        client = self._get_client()
        if client is None:
            return None

        key = _version_key(o_id)

        try:
            version = client.get(key)
            if version is not None:
                return str(version)

            if client.set(key, "1", nx=True):
                return "1"

            version = client.get(key)
            return str(version) if version is not None else None
        except Exception:
            logger.exception("Failed to read cast config cache version for org_id=%s", o_id)
            return None


@lru_cache(maxsize=1)
def get_cast_config_cache() -> CastConfigCache:
    return CastConfigCache()


def _should_use_shared_cache() -> bool:
    return not bool(app_settings.TESTING)


def load_cast_configs(db: Any, o_id: int) -> list[FieldCastConfig]:
    if not _should_use_shared_cache():
        return _load_cast_configs_from_db(db, o_id)
    return get_cast_config_cache().load(db, o_id)


def invalidate_cast_config_cache(o_id: int) -> bool:
    if not _should_use_shared_cache():
        return False
    return get_cast_config_cache().invalidate(o_id)


def reset_cast_config_cache() -> None:
    get_cast_config_cache().clear()
    get_cast_config_cache.cache_clear()
    get_cast_config_cache_client.cache_clear()
