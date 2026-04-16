import bcrypt
from fastapi.testclient import TestClient

from ezrules.backend.api_v2.auth.jwt import create_access_token
from ezrules.backend.api_v2.main import app
from ezrules.core.permissions import PermissionManager
from ezrules.core.permissions_constants import PermissionAction
from ezrules.models.backend_core import AllowedOutcome, FieldObservation, FieldTypeConfig, Organisation, Role, User


def _build_rules_client(session):
    hashed_password = bcrypt.hashpw("verifypass".encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    org = session.query(Organisation).filter(Organisation.o_id == 1).first()
    if not org:
        org = Organisation(o_id=1, name="Test Org")
        session.add(org)
        session.commit()

    for severity_rank, outcome_name in enumerate(("RELEASE", "HOLD", "CANCEL"), start=1):
        existing_outcome = (
            session.query(AllowedOutcome)
            .filter(AllowedOutcome.o_id == int(org.o_id), AllowedOutcome.outcome_name == outcome_name)
            .first()
        )
        if existing_outcome is None:
            session.add(AllowedOutcome(outcome_name=outcome_name, severity_rank=severity_rank, o_id=int(org.o_id)))
    session.commit()

    role = session.query(Role).filter(Role.name == "verify_warning_manager").first()
    if not role:
        role = Role(name="verify_warning_manager", description="Can verify and test rules")
        session.add(role)
        session.commit()

    user = session.query(User).filter(User.email == "verify-warning@example.com").first()
    if not user:
        user = User(
            email="verify-warning@example.com",
            password=hashed_password,
            active=True,
            fs_uniquifier="verify-warning@example.com",
            o_id=1,
        )
        user.roles.append(role)
        session.add(user)
        session.commit()

    PermissionManager.db_session = session
    PermissionManager.init_default_actions()
    PermissionManager.grant_permission(role.id, PermissionAction.VIEW_RULES)

    token = create_access_token(user_id=int(user.id), email=str(user.email), roles=[role.name], org_id=int(user.o_id))

    client = TestClient(app)
    client.test_data = {"token": token, "session": session, "org": org}  # type: ignore[attr-defined]
    return client


class TestRuleVerifyWarnings:
    def test_verify_warns_when_field_has_never_been_observed(self, session):
        client = _build_rules_client(session)
        token = client.test_data["token"]  # type: ignore[attr-defined]

        response = client.post(
            "/api/v2/rules/verify",
            headers={"Authorization": f"Bearer {token}"},
            json={"rule_source": "return $never_seen > 0"},
        )

        client.close()

        assert response.status_code == 200
        data = response.json()
        assert data["params"] == ["never_seen"]
        assert len(data["warnings"]) == 1
        assert "never_seen" in data["warnings"][0]

    def test_verify_does_not_warn_when_field_has_been_observed(self, session):
        client = _build_rules_client(session)
        token = client.test_data["token"]  # type: ignore[attr-defined]
        org = client.test_data["org"]  # type: ignore[attr-defined]

        session.add(FieldObservation(field_name="amount", observed_json_type="int", o_id=org.o_id))
        session.commit()

        response = client.post(
            "/api/v2/rules/verify",
            headers={"Authorization": f"Bearer {token}"},
            json={"rule_source": "return $amount > 0"},
        )

        client.close()

        assert response.status_code == 200
        data = response.json()
        assert data["params"] == ["amount"]
        assert data["warnings"] == []


class TestRuleTestNormalizationErrors:
    def test_rules_test_returns_required_field_error(self, session):
        client = _build_rules_client(session)
        token = client.test_data["token"]  # type: ignore[attr-defined]
        org = client.test_data["org"]  # type: ignore[attr-defined]

        session.add(FieldTypeConfig(field_name="amount", configured_type="integer", required=True, o_id=org.o_id))
        session.commit()

        response = client.post(
            "/api/v2/rules/test",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "rule_source": "return True",
                "test_json": "{}",
            },
        )

        client.close()

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "error"
        assert "amount" in data["reason"]
        assert "normalization" in data["reason"].lower()

    def test_rules_test_returns_explicit_missing_lookup_error(self, session):
        client = _build_rules_client(session)
        token = client.test_data["token"]  # type: ignore[attr-defined]

        response = client.post(
            "/api/v2/rules/test",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "rule_source": 'return $country == "US"',
                "test_json": '{"amount": 100}',
            },
        )

        client.close()

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "error"
        assert "country" in data["reason"]
        assert "lookup failed" in data["reason"]
