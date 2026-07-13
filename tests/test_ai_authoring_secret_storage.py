import runpy
from dataclasses import replace
from pathlib import Path

import pytest
import sqlalchemy as sa

from ezrules.backend import runtime_settings
from ezrules.backend.runtime_settings import (
    AI_AUTHORING_API_KEY_KEY,
    get_ai_authoring_api_key,
    has_ai_authoring_api_key,
    set_ai_authoring_api_key,
)
from ezrules.core.secret_encryption import SECRET_ENCRYPTION_PREFIX, decrypt_secret, encrypt_secret
from ezrules.models.backend_core import Organisation, RuntimeSetting

_MIGRATION_PATH = (
    Path(__file__).resolve().parents[1] / "alembic" / "versions" / "20260713_0039_encrypt_ai_authoring_api_keys.py"
)


def test_secret_encryption_round_trip_and_tamper_rejection():
    encrypted = encrypt_secret("sk-provider-secret")

    assert encrypted.startswith(SECRET_ENCRYPTION_PREFIX)
    assert "sk-provider-secret" not in encrypted
    assert decrypt_secret(encrypted) == "sk-provider-secret"

    with pytest.raises(ValueError, match="could not be decrypted"):
        decrypt_secret(encrypted[:-1] + ("A" if encrypted[-1] != "A" else "B"))


def test_ai_authoring_api_key_is_encrypted_in_raw_database_storage(session):
    org = Organisation(name="Encrypted AI Secret Org")
    session.add(org)
    session.commit()

    set_ai_authoring_api_key(session, "sk-provider-secret", int(org.o_id))
    session.commit()

    stored = (
        session.execute(
            sa.text(
                """
            SELECT value, value_type
            FROM runtime_settings
            WHERE key = :key AND o_id = :o_id
            """
            ),
            {"key": AI_AUTHORING_API_KEY_KEY, "o_id": int(org.o_id)},
        )
        .mappings()
        .one()
    )
    assert stored["value_type"] == "secret"
    assert str(stored["value"]).startswith(SECRET_ENCRYPTION_PREFIX)
    assert "sk-provider-secret" not in str(stored["value"])

    session.expire_all()
    setting = (
        session.query(RuntimeSetting)
        .filter(RuntimeSetting.key == AI_AUTHORING_API_KEY_KEY, RuntimeSetting.o_id == int(org.o_id))
        .one()
    )
    assert setting.value == "sk-provider-secret"
    assert "sk-provider-secret" not in repr(setting)
    assert get_ai_authoring_api_key(session, int(org.o_id)) == "sk-provider-secret"


def test_ai_authoring_secret_preserves_fallback_clear_and_fail_closed_semantics(session, monkeypatch):
    spec = runtime_settings._RUNTIME_SETTING_SPECS[AI_AUTHORING_API_KEY_KEY]
    monkeypatch.setitem(
        runtime_settings._RUNTIME_SETTING_SPECS,
        AI_AUTHORING_API_KEY_KEY,
        replace(spec, default="sk-environment-default"),
    )

    fallback_org = Organisation(name="AI Secret Fallback Org")
    corrupt_org = Organisation(name="AI Secret Corrupt Org")
    session.add_all([fallback_org, corrupt_org])
    session.commit()

    assert get_ai_authoring_api_key(session, int(fallback_org.o_id)) == "sk-environment-default"

    set_ai_authoring_api_key(session, "", int(fallback_org.o_id))
    session.commit()
    assert get_ai_authoring_api_key(session, int(fallback_org.o_id)) == ""
    assert has_ai_authoring_api_key(session, int(fallback_org.o_id)) is False

    cleared_raw_value = session.execute(
        sa.text(
            """
            SELECT value
            FROM runtime_settings
            WHERE key = :key AND o_id = :o_id
            """
        ),
        {"key": AI_AUTHORING_API_KEY_KEY, "o_id": int(fallback_org.o_id)},
    ).scalar_one()
    assert str(cleared_raw_value).startswith(SECRET_ENCRYPTION_PREFIX)
    assert cleared_raw_value != ""

    session.execute(
        sa.text(
            """
            INSERT INTO runtime_settings (key, o_id, value_type, value, created_at, updated_at)
            VALUES (:key, :o_id, 'secret', 'plaintext-or-corrupt', NOW(), NOW())
            """
        ),
        {"key": AI_AUTHORING_API_KEY_KEY, "o_id": int(corrupt_org.o_id)},
    )
    session.commit()
    session.expire_all()

    assert get_ai_authoring_api_key(session, int(corrupt_org.o_id)) == ""
    assert has_ai_authoring_api_key(session, int(corrupt_org.o_id)) is False


def test_ai_authoring_secret_migration_round_trip_and_placeholder_refusal(session, monkeypatch):
    migration = runpy.run_path(str(_MIGRATION_PATH))
    org = Organisation(name="AI Secret Migration Org")
    session.add(org)
    session.commit()
    session.execute(
        sa.text(
            """
            INSERT INTO runtime_settings (key, o_id, value_type, value, created_at, updated_at)
            VALUES (:key, :o_id, 'string', :value, NOW(), NOW())
            """
        ),
        {"key": AI_AUTHORING_API_KEY_KEY, "o_id": int(org.o_id), "value": "sk-migration-secret"},
    )
    session.flush()

    monkeypatch.setattr(migration["op"], "get_bind", session.connection)
    with monkeypatch.context() as placeholder_patch:
        placeholder_patch.setattr(migration["app_settings"], "APP_SECRET", "alembic-placeholder-secret")
        with pytest.raises(RuntimeError, match="EZRULES_APP_SECRET must be set"):
            migration["upgrade"]()

    migration["upgrade"]()
    upgraded = (
        session.execute(
            sa.text(
                """
            SELECT value, value_type
            FROM runtime_settings
            WHERE key = :key AND o_id = :o_id
            """
            ),
            {"key": AI_AUTHORING_API_KEY_KEY, "o_id": int(org.o_id)},
        )
        .mappings()
        .one()
    )
    assert upgraded["value_type"] == "secret"
    assert str(upgraded["value"]).startswith(SECRET_ENCRYPTION_PREFIX)
    assert decrypt_secret(str(upgraded["value"])) == "sk-migration-secret"

    migration["downgrade"]()
    downgraded = (
        session.execute(
            sa.text(
                """
            SELECT value, value_type
            FROM runtime_settings
            WHERE key = :key AND o_id = :o_id
            """
            ),
            {"key": AI_AUTHORING_API_KEY_KEY, "o_id": int(org.o_id)},
        )
        .mappings()
        .one()
    )
    assert dict(downgraded) == {"value": "sk-migration-secret", "value_type": "string"}

    migration["upgrade"]()
