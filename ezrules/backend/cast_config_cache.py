import logging
from dataclasses import dataclass
from functools import lru_cache
from threading import Lock
from time import monotonic
from typing import Any

from redis import Redis

from ezrules.backend.runtime_settings import get_field_type_config_version
from ezrules.core.type_casting import FieldCastConfig, FieldType
from ezrules.models.backend_core import FieldTypeConfig
from ezrules.settings import app_settings

logger = logging.getLogger(__name__)

_CAST_CONFIG_VERSION_KEY_PREFIX = "ezrules:field_type_config_version"
_LOCAL_CACHE_MAX_AGE_SECONDS = 600


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
    loaded_at: float


class CastConfigCache:
    def __init__(self, client_getter=None):
        self._client_getter = client_getter or get_cast_config_cache_client
        self._entries: dict[int, _CacheEntry] = {}
        self._lock = Lock()

    def load(self, db: Any, o_id: int) -> list[FieldCastConfig]:
        cached_entry = self._get_entry(o_id)
        redis_version = self._read_version(o_id)

        if (
            cached_entry is not None
            and redis_version is not None
            and cached_entry.version == redis_version
            and not self._is_expired(cached_entry)
        ):
            return cached_entry.configs

        durable_version: str | None = None
        if (
            redis_version is None
            or cached_entry is None
            or cached_entry.version != redis_version
            or self._is_expired(cached_entry)
        ):
            durable_version = self._read_durable_version(db, o_id)
            if redis_version != durable_version:
                self._write_version(o_id, durable_version)

        version = durable_version or redis_version
        if version is None:
            self.invalidate_local(o_id)
            return _load_cast_configs_from_db(db, o_id)

        if cached_entry is not None and cached_entry.version == version:
            self._store_entry(o_id, version, cached_entry.configs)
            return cached_entry.configs

        configs = _load_cast_configs_from_db(db, o_id)
        self._store_entry(o_id, version, configs)
        return configs

    def publish(self, o_id: int, version: int) -> bool:
        self.invalidate_local(o_id)
        return self._write_version(o_id, str(version))

    def invalidate_local(self, o_id: int) -> None:
        with self._lock:
            self._entries.pop(o_id, None)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    def _get_entry(self, o_id: int) -> _CacheEntry | None:
        with self._lock:
            return self._entries.get(o_id)

    def _store_entry(self, o_id: int, version: str, configs: list[FieldCastConfig]) -> None:
        with self._lock:
            self._entries[o_id] = _CacheEntry(version=version, configs=configs, loaded_at=monotonic())

    def _is_expired(self, entry: _CacheEntry) -> bool:
        return (monotonic() - entry.loaded_at) >= _LOCAL_CACHE_MAX_AGE_SECONDS

    def _get_client(self) -> Redis | None:
        try:
            return self._client_getter()
        except Exception:
            logger.exception("Failed to create cast config cache Redis client")
            return None

    def _read_durable_version(self, db: Any, o_id: int) -> str:
        return str(get_field_type_config_version(db, o_id))

    def _read_version(self, o_id: int) -> str | None:
        client = self._get_client()
        if client is None:
            return None

        key = _version_key(o_id)

        try:
            version = client.get(key)
            return str(version) if version is not None else None
        except Exception:
            logger.exception("Failed to read cast config cache version for org_id=%s", o_id)
            return None

    def _write_version(self, o_id: int, version: str) -> bool:
        client = self._get_client()
        if client is None:
            return False

        try:
            client.set(_version_key(o_id), version)
        except Exception:
            logger.exception("Failed to publish cast config cache version for org_id=%s", o_id)
            return False

        return True


@lru_cache(maxsize=1)
def get_cast_config_cache() -> CastConfigCache:
    return CastConfigCache()


def _should_use_shared_cache() -> bool:
    return not bool(app_settings.TESTING)


def load_cast_configs(db: Any, o_id: int) -> list[FieldCastConfig]:
    if not _should_use_shared_cache():
        return _load_cast_configs_from_db(db, o_id)
    return get_cast_config_cache().load(db, o_id)


def publish_cast_config_version(o_id: int, version: int) -> bool:
    if not _should_use_shared_cache():
        return False
    return get_cast_config_cache().publish(o_id, version)


def reset_cast_config_cache() -> None:
    get_cast_config_cache().clear()
    get_cast_config_cache.cache_clear()
    get_cast_config_cache_client.cache_clear()
