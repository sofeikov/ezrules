"""Cross-cutting API v2 contract regression tests.

Run ``uv run python tests/test_api_v2_contract_regressions.py`` after an
intentional API contract change to regenerate the normalized inventory.
"""

import json
import re
import uuid
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from ezrules.backend.api_v2.auth.jwt import create_access_token
from ezrules.backend.api_v2.main import app
from ezrules.models.backend_core import Organisation, User
from ezrules.settings import app_settings

SNAPSHOT_PATH = Path(__file__).parent / "contracts" / "api_v2_openapi_inventory.json"
PUBLIC_OPERATIONS = {
    ("POST", "/api/v2/auth/accept-invite"),
    ("POST", "/api/v2/auth/forgot-password"),
    ("POST", "/api/v2/auth/login"),
    ("POST", "/api/v2/auth/refresh"),
    ("POST", "/api/v2/auth/reset-password"),
}
OAUTH_SECURITY = [["OAuth2PasswordBearer"]]
EVALUATOR_SECURITY = [["ApiKeyAuth"], ["OAuth2PasswordBearer"]]
REPRESENTATIVE_PROTECTED_READS = (
    "/api/v2/alerts/rules",
    "/api/v2/analytics/labels-summary",
    "/api/v2/api-keys",
    "/api/v2/audit",
    "/api/v2/cases",
    "/api/v2/features",
    "/api/v2/labels",
    "/api/v2/outcomes",
    "/api/v2/roles",
    "/api/v2/rules",
    "/api/v2/settings/runtime",
    "/api/v2/tested-events",
    "/api/v2/user-lists",
    "/api/v2/users",
)


def _operation_inventory(schema: dict[str, Any]) -> list[dict[str, Any]]:
    operations = []
    for path, path_item in schema["paths"].items():
        inherited_parameters = path_item.get("parameters", [])
        for method, operation in path_item.items():
            if method == "parameters":
                continue

            parameters = [*inherited_parameters, *operation.get("parameters", [])]
            tracked_parameters = []
            for parameter in parameters:
                if parameter["in"] not in {"path", "query"}:
                    continue
                parameter_schema = parameter.get("schema", {})
                if "anyOf" in parameter_schema:
                    parameter_schema = next(
                        (candidate for candidate in parameter_schema["anyOf"] if candidate.get("type") != "null"),
                        parameter_schema,
                    )
                tracked_parameters.append(
                    {
                        "in": parameter["in"],
                        "name": parameter["name"],
                        "required": parameter.get("required", False),
                        "schema": {
                            key: parameter_schema[key]
                            for key in ("default", "maximum", "minimum", "type")
                            if key in parameter_schema
                        },
                    }
                )

            security = sorted(sorted(requirement) for requirement in operation.get("security", []))
            request_content = sorted(operation.get("requestBody", {}).get("content", {}).keys())
            operations.append(
                {
                    "method": method.upper(),
                    "operation_id": operation["operationId"],
                    "parameters": sorted(
                        tracked_parameters,
                        key=lambda item: (item["in"], item["name"]),
                    ),
                    "path": path,
                    "request_content": request_content,
                    "security": security,
                    "success_responses": sorted(
                        code for code in operation["responses"] if code.isdigit() and 200 <= int(code) < 300
                    ),
                }
            )
    return sorted(operations, key=lambda item: (item["path"], item["method"]))


def _assert_standard_error(response, *, status_code: int, detail_type: type) -> None:
    assert response.status_code == status_code
    assert response.headers["content-type"].startswith("application/json")
    payload = response.json()
    assert set(payload) == {"detail"}
    assert isinstance(payload["detail"], detail_type)


@pytest.fixture
def contract_user(session) -> User:
    org = session.query(Organisation).one()
    email = f"contract-{uuid.uuid4().hex}@example.com"
    user = User(
        email=email,
        password="not-used",
        active=True,
        fs_uniquifier=email,
        o_id=int(org.o_id),
    )
    session.add(user)
    session.commit()
    return user


def _access_token(user: User, *, org_id: int | None = None) -> str:
    return create_access_token(
        user_id=int(user.id),
        email=str(user.email),
        roles=[],
        org_id=int(user.o_id) if org_id is None else org_id,
    )


def test_openapi_operation_inventory_matches_snapshot() -> None:
    expected = json.loads(SNAPSHOT_PATH.read_text())

    assert _operation_inventory(app.openapi()) == expected


def test_openapi_inventory_tolerates_null_only_any_of_parameter() -> None:
    schema = {
        "paths": {
            "/example": {
                "get": {
                    "operationId": "example",
                    "parameters": [
                        {
                            "in": "query",
                            "name": "cursor",
                            "schema": {"anyOf": [{"type": "null"}]},
                        }
                    ],
                    "responses": {"200": {"description": "ok"}},
                }
            }
        }
    }

    assert _operation_inventory(schema)[0]["parameters"] == [
        {
            "in": "query",
            "name": "cursor",
            "required": False,
            "schema": {},
        }
    ]


def test_openapi_has_unique_operation_ids_and_no_undeclared_public_routes() -> None:
    operations = _operation_inventory(app.openapi())
    operation_ids = [operation["operation_id"] for operation in operations]
    public_operations = {
        (operation["method"], operation["path"])
        for operation in operations
        if operation["path"].startswith("/api/v2") and not operation["security"]
    }

    assert len(operation_ids) == len(set(operation_ids))
    assert public_operations == PUBLIC_OPERATIONS
    assert all(
        operation["security"]
        == (
            EVALUATOR_SECURITY
            if (operation["method"], operation["path"]) == ("POST", "/api/v2/evaluate")
            else OAUTH_SECURITY
        )
        for operation in operations
        if operation["path"].startswith("/api/v2") and (operation["method"], operation["path"]) not in PUBLIC_OPERATIONS
    )


def test_evaluator_openapi_declares_api_key_or_oauth_security() -> None:
    schema = app.openapi()

    assert schema["components"]["securitySchemes"]["ApiKeyAuth"] == {
        "type": "apiKey",
        "in": "header",
        "name": "X-API-Key",
    }
    assert schema["paths"]["/api/v2/evaluate"]["post"]["security"] == [
        {"ApiKeyAuth": []},
        {"OAuth2PasswordBearer": []},
    ]
    assert schema["paths"]["/api/v2/event-tests"]["post"]["security"] == [
        {"OAuth2PasswordBearer": []},
    ]


def test_openapi_declares_validation_errors_for_validated_inputs() -> None:
    schema = app.openapi()
    missing_validation_response = []
    for path, path_item in schema["paths"].items():
        for method, operation in path_item.items():
            if method == "parameters":
                continue
            has_validated_input = bool(
                path_item.get("parameters") or operation.get("parameters") or operation.get("requestBody")
            )
            if has_validated_input and "422" not in operation["responses"]:
                missing_validation_response.append(f"{method.upper()} {path}")

    assert missing_validation_response == []


@pytest.mark.parametrize("path", REPRESENTATIVE_PROTECTED_READS)
def test_protected_route_matrix_rejects_missing_authentication(path: str) -> None:
    with TestClient(app) as client:
        response = client.get(path)

    _assert_standard_error(response, status_code=401, detail_type=str)
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize("path", REPRESENTATIVE_PROTECTED_READS)
def test_protected_route_matrix_rejects_mismatched_tenant_claim(
    session,
    contract_user: User,
    path: str,
) -> None:
    token = _access_token(contract_user, org_id=int(contract_user.o_id) + 1)

    with TestClient(app) as client:
        response = client.get(path, headers={"Authorization": f"Bearer {token}"})

    _assert_standard_error(response, status_code=401, detail_type=str)
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize("path", REPRESENTATIVE_PROTECTED_READS)
def test_protected_route_matrix_rejects_missing_permissions(
    session,
    contract_user: User,
    path: str,
) -> None:
    token = _access_token(contract_user)

    with TestClient(app) as client:
        response = client.get(path, headers={"Authorization": f"Bearer {token}"})

    _assert_standard_error(response, status_code=403, detail_type=str)
    assert response.json()["detail"] == "Permission denied"


@pytest.mark.parametrize(
    ("content", "content_type", "expected_error_type"),
    (
        (b'{"email":', "application/json", "json_invalid"),
        (b'{"email":"user@example.com"}', "text/plain", "model_attributes_type"),
        (b"{}", "application/json", "missing"),
    ),
)
def test_json_framing_and_validation_errors_use_standard_shape(
    content: bytes,
    content_type: str,
    expected_error_type: str,
) -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/v2/auth/forgot-password",
            content=content,
            headers={"Content-Type": content_type},
        )

    _assert_standard_error(response, status_code=422, detail_type=list)
    assert expected_error_type in {error["type"] for error in response.json()["detail"]}


def test_login_rejects_json_instead_of_oauth_form_data() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/v2/auth/login",
            json={"username": "admin@example.com", "password": "secret"},
        )

    _assert_standard_error(response, status_code=422, detail_type=list)
    missing_fields = {error["loc"][-1] for error in response.json()["detail"] if error["type"] == "missing"}
    assert missing_fields == {"password", "username"}


def test_body_size_limit_rejects_oversized_payload_before_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(app_settings, "MAX_BODY_SIZE_KB", 1)
    oversized_body = b'{"email":"' + (b"a" * 1024) + b'"}'

    with TestClient(app) as client:
        response = client.post(
            "/api/v2/auth/forgot-password",
            content=oversized_body,
            headers={"Content-Type": "application/json"},
        )

    _assert_standard_error(response, status_code=413, detail_type=str)
    assert response.json()["detail"] == "Request body too large"


def test_body_within_limit_reaches_schema_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(app_settings, "MAX_BODY_SIZE_KB", 1)
    body = b"{" + (b" " * 1022) + b"}"

    with TestClient(app) as client:
        response = client.post(
            "/api/v2/auth/forgot-password",
            content=body,
            headers={"Content-Type": "application/json"},
        )

    _assert_standard_error(response, status_code=422, detail_type=list)


def test_evaluator_accepts_supported_nested_payload_depth_before_authentication() -> None:
    nested: dict[str, Any] = {"value": "leaf"}
    for index in range(32):
        nested = {f"level_{index}": nested}

    with TestClient(app) as client:
        response = client.post(
            "/api/v2/evaluate",
            json={
                "transaction_id": "nested-contract",
                "effective_at": "2026-07-14T00:00:00Z",
                "event_data": nested,
            },
        )

    _assert_standard_error(response, status_code=401, detail_type=str)
    assert response.json()["detail"] == "Authentication required"


def test_pagination_parameters_are_bounded_in_openapi() -> None:
    operations = _operation_inventory(app.openapi())
    pagination_parameters = [
        parameter
        for operation in operations
        for parameter in operation["parameters"]
        if parameter["in"] == "query" and parameter["name"] in {"cursor", "limit", "max_events", "max_hops", "offset"}
    ]

    assert pagination_parameters
    assert all(parameter["schema"].get("minimum") is not None for parameter in pagination_parameters)
    assert all(
        parameter["schema"].get("maximum") is not None
        for parameter in pagination_parameters
        if parameter["name"] in {"limit", "max_events", "max_hops"}
    )
    assert all(
        parameter["schema"].get("default") is not None
        for parameter in pagination_parameters
        if parameter["name"] in {"limit", "max_events", "max_hops", "offset"}
    )


def test_path_parameter_names_match_route_templates() -> None:
    operations = _operation_inventory(app.openapi())
    for operation in operations:
        declared = {parameter["name"] for parameter in operation["parameters"] if parameter["in"] == "path"}
        templated = set(re.findall(r"{([^}]+)}", operation["path"]))
        assert declared == templated, f"{operation['method']} {operation['path']}"


if __name__ == "__main__":
    inventory = _operation_inventory(app.openapi())
    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_PATH.write_text(f"{json.dumps(inventory, indent=2, sort_keys=True)}\n")
