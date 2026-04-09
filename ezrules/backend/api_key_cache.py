import hashlib
import logging
from dataclasses import dataclass
from functools import lru_cache
from threading import Lock
from time import monotonic
from typing import Any

from redis import Redis

from ezrules.backend.runtime_settings import get_api_key_cache_version
from ezrules.models.backend_core import ApiKey
from ezrules.settings import app_settings

logger = logging.getLogger(__name__)

_API_KEY_AUTH_VERSION_KEY_PREFIX = "ezrules:api_key_auth_version"
_LOCAL_CACHE_MAX_AGE_SECONDS = 600


def _api_key_cache_url() -> str:
    return app_settings.OBSERVATION_QUEUE_REDIS_URL or app_settings.CELERY_BROKER_URL


@lru_cache(maxsize=1)
def get_api_key_auth_cache_client() -> Redis:
    return Redis.from_url(_api_key_cache_url(), decode_responses=True)


@dataclass(frozen=True)
class ApiKeyAuthMetadata:
    org_id: int


def _hash_api_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode()).hexdigest()


def _load_api_key_auth_metadata_from_db(db: Any, key_hash: str) -> ApiKeyAuthMetadata | None:
    row = db.query(ApiKey.o_id).filter(ApiKey.key_hash == key_hash, ApiKey.revoked_at.is_(None)).first()
    if row is None:
        return None
    return ApiKeyAuthMetadata(org_id=int(row[0]))


def _version_key(org_id: int) -> str:
    return f"{_API_KEY_AUTH_VERSION_KEY_PREFIX}:{org_id}"


@dataclass(frozen=True)
class _CacheEntry:
    version: str
    metadata: ApiKeyAuthMetadata
    loaded_at: float


class ApiKeyAuthCache:
    def __init__(self, client_getter=None):
        self._client_getter = client_getter or get_api_key_auth_cache_client
        self._entries: dict[str, _CacheEntry] = {}
        self._lock = Lock()

    def load(self, db: Any, api_key: str) -> ApiKeyAuthMetadata | None:
        return self.load_hashed(db, _hash_api_key(api_key))

    def load_hashed(self, db: Any, key_hash: str) -> ApiKeyAuthMetadata | None:
        cached_entry = self._get_entry(key_hash)
        if cached_entry is not None:
            cached_org_id = cached_entry.metadata.org_id
            is_expired = self._is_expired(cached_entry)
            redis_version = self._read_version(cached_org_id)
            if redis_version is not None and cached_entry.version == redis_version and not is_expired:
                return cached_entry.metadata

            durable_version: str | None = None
            if redis_version is None or cached_entry.version != redis_version or is_expired:
                durable_version = self._read_durable_version(db, cached_org_id)
                if redis_version != durable_version:
                    self._write_version(cached_org_id, durable_version)

            current_version = durable_version or redis_version
            if current_version is not None and cached_entry.version == current_version:
                self._store_entry(key_hash, current_version, cached_entry.metadata)
                return cached_entry.metadata

        metadata = _load_api_key_auth_metadata_from_db(db, key_hash)
        if metadata is None:
            self.invalidate_local_key_hash(key_hash)
            return None

        version = self._resolve_version(db, metadata.org_id)
        if version is not None:
            self._store_entry(key_hash, version, metadata)
        return metadata

    def publish(self, org_id: int, version: int) -> bool:
        self.invalidate_local_org(org_id)
        return self._write_version(org_id, str(version))

    def invalidate_local_key_hash(self, key_hash: str) -> None:
        with self._lock:
            self._entries.pop(key_hash, None)

    def invalidate_local_org(self, org_id: int) -> None:
        with self._lock:
            self._entries = {
                key_hash: entry for key_hash, entry in self._entries.items() if entry.metadata.org_id != org_id
            }

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    def _get_entry(self, key_hash: str) -> _CacheEntry | None:
        with self._lock:
            return self._entries.get(key_hash)

    def _store_entry(self, key_hash: str, version: str, metadata: ApiKeyAuthMetadata) -> None:
        with self._lock:
            self._entries[key_hash] = _CacheEntry(version=version, metadata=metadata, loaded_at=monotonic())

    def _is_expired(self, entry: _CacheEntry) -> bool:
        return (monotonic() - entry.loaded_at) >= _LOCAL_CACHE_MAX_AGE_SECONDS

    def _get_client(self) -> Redis | None:
        try:
            return self._client_getter()
        except Exception:
            logger.exception("Failed to create API-key auth cache Redis client")
            return None

    def _read_durable_version(self, db: Any, org_id: int) -> str:
        return str(get_api_key_cache_version(db, org_id))

    def _resolve_version(self, db: Any, org_id: int) -> str | None:
        redis_version = self._read_version(org_id)
        if redis_version is not None:
            return redis_version

        durable_version = self._read_durable_version(db, org_id)
        self._write_version(org_id, durable_version)
        return durable_version

    def _read_version(self, org_id: int) -> str | None:
        client = self._get_client()
        if client is None:
            return None

        try:
            version = client.get(_version_key(org_id))
            return str(version) if version is not None else None
        except Exception:
            logger.exception("Failed to read API-key auth cache version for org_id=%s", org_id)
            return None

    def _write_version(self, org_id: int, version: str) -> bool:
        client = self._get_client()
        if client is None:
            return False

        try:
            client.set(_version_key(org_id), version)
        except Exception:
            logger.exception("Failed to publish API-key auth cache version for org_id=%s", org_id)
            return False

        return True


@lru_cache(maxsize=1)
def get_api_key_auth_cache() -> ApiKeyAuthCache:
    return ApiKeyAuthCache()


def _should_use_shared_cache() -> bool:
    return not bool(app_settings.TESTING)


def load_api_key_auth_metadata(db: Any, api_key: str) -> ApiKeyAuthMetadata | None:
    if not _should_use_shared_cache():
        return _load_api_key_auth_metadata_from_db(db, _hash_api_key(api_key))
    return get_api_key_auth_cache().load(db, api_key)


def publish_api_key_auth_version(org_id: int, version: int) -> bool:
    if not _should_use_shared_cache():
        get_api_key_auth_cache().invalidate_local_org(org_id)
        return False
    return get_api_key_auth_cache().publish(org_id, version)


def reset_api_key_auth_cache() -> None:
    get_api_key_auth_cache().clear()
    get_api_key_auth_cache.cache_clear()
    get_api_key_auth_cache_client.cache_clear()
