"""
Regression tests for evaluator auth and org-context deduplication.
"""

import hashlib
import secrets
import uuid

import pytest
from fastapi.testclient import TestClient

from ezrules.backend.api_v2 import main as main_module
from ezrules.backend.api_v2.auth import dependencies as auth_dependencies
from ezrules.backend.api_v2.auth.jwt import create_access_token
from ezrules.backend.api_v2.main import app
from ezrules.backend.api_v2.routes import evaluator as evaluator_router
from ezrules.backend.rule_executors.executors import LocalRuleExecutorSQL
from ezrules.models.backend_core import ApiKey, Organisation, User


@pytest.fixture(scope="function")
def org(session):
    return session.query(Organisation).one()


@pytest.fixture(scope="function")
def live_api_key(session, org):
    raw_key = "ezrk_" + secrets.token_hex(32)
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    api_key = ApiKey(
        gid=str(uuid.uuid4()),
        key_hash=key_hash,
        label="dedup-test-key",
        o_id=org.o_id,
    )
    session.add(api_key)
    session.commit()
    return raw_key


@pytest.fixture(scope="function")
def bearer_token(session, org):
    user = User(
        email=f"evaluator-dedup-{uuid.uuid4().hex[:8]}@example.com",
        password="not-used-in-this-test",
        active=True,
        fs_uniquifier=f"evaluator-dedup-{uuid.uuid4().hex}",
        o_id=org.o_id,
    )
    session.add(user)
    session.commit()
    return create_access_token(
        user_id=int(user.id),
        email=str(user.email),
        roles=[],
        org_id=int(user.o_id),
    )


def _install_counting_wrappers(monkeypatch: pytest.MonkeyPatch) -> dict[str, int]:
    counters = {
        "api_key_lookups": 0,
        "access_token_lookups": 0,
        "org_context_binds": 0,
    }

    original_api_key_lookup = auth_dependencies.get_org_id_for_api_key
    original_access_token_lookup = auth_dependencies.get_org_id_for_access_token
    original_bind_request_org_context = auth_dependencies.bind_request_org_context

    def counted_api_key_lookup(api_key: str, db):
        counters["api_key_lookups"] += 1
        return original_api_key_lookup(api_key, db)

    def counted_access_token_lookup(token: str, db):
        counters["access_token_lookups"] += 1
        return original_access_token_lookup(token, db)

    def counted_bind_request_org_context(db, org_id: int):
        counters["org_context_binds"] += 1
        return original_bind_request_org_context(db, org_id)

    monkeypatch.setattr(auth_dependencies, "get_org_id_for_api_key", counted_api_key_lookup)
    monkeypatch.setattr(main_module, "get_org_id_for_api_key", counted_api_key_lookup)
    monkeypatch.setattr(auth_dependencies, "get_org_id_for_access_token", counted_access_token_lookup)
    monkeypatch.setattr(main_module, "get_org_id_for_access_token", counted_access_token_lookup)
    monkeypatch.setattr(auth_dependencies, "bind_request_org_context", counted_bind_request_org_context)
    monkeypatch.setattr(main_module, "bind_request_org_context", counted_bind_request_org_context)

    return counters


def test_evaluate_api_key_auth_and_org_context_are_resolved_once(session, org, live_api_key, monkeypatch):
    counters = _install_counting_wrappers(monkeypatch)
    evaluator_router._lre = LocalRuleExecutorSQL(db=session, o_id=org.o_id)

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v2/evaluate",
                json={
                    "event_id": "dedup-api-key",
                    "event_timestamp": 1234567890,
                    "event_data": {},
                },
                headers={"X-API-Key": live_api_key},
            )
    finally:
        evaluator_router._lre = None

    assert response.status_code == 200
    assert counters == {
        "api_key_lookups": 1,
        "access_token_lookups": 0,
        "org_context_binds": 1,
    }


def test_evaluate_bearer_auth_and_org_context_are_resolved_once(session, org, bearer_token, monkeypatch):
    counters = _install_counting_wrappers(monkeypatch)
    evaluator_router._lre = LocalRuleExecutorSQL(db=session, o_id=org.o_id)

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v2/evaluate",
                json={
                    "event_id": "dedup-bearer",
                    "event_timestamp": 1234567890,
                    "event_data": {},
                },
                headers={"Authorization": f"Bearer {bearer_token}"},
            )
    finally:
        evaluator_router._lre = None

    assert response.status_code == 200
    assert counters == {
        "api_key_lookups": 0,
        "access_token_lookups": 1,
        "org_context_binds": 1,
    }
