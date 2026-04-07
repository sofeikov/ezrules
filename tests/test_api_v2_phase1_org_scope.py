import uuid

import bcrypt
from fastapi.testclient import TestClient

from ezrules.backend.api_v2.auth.jwt import create_access_token, decode_token
from ezrules.backend.api_v2.main import app
from ezrules.core.permissions import PermissionManager
from ezrules.core.permissions_constants import PermissionAction
from ezrules.models.backend_core import (
    AllowedOutcome,
    FieldObservation,
    FieldTypeConfig,
    Label,
    Organisation,
    Role,
    TestingRecordLog,
    User,
    UserList,
)


def _unique_email(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}@example.com"


def _grant_permissions(session, role: Role, permissions: list[PermissionAction]) -> None:
    PermissionManager.db_session = session
    PermissionManager.init_default_actions()
    for permission in permissions:
        PermissionManager.grant_permission(int(role.id), permission)


def _create_user(
    session,
    *,
    org_id: int,
    email: str,
    password: str = "phase1pass",
    permissions: list[PermissionAction] | None = None,
) -> User:
    hashed_password = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    user = User(
        email=email,
        password=hashed_password,
        active=True,
        fs_uniquifier=str(uuid.uuid4()),
        o_id=org_id,
    )

    if permissions:
        role = Role(
            name=f"phase1-role-{uuid.uuid4().hex[:8]}",
            description="Phase 1 test role",
            o_id=org_id,
        )
        session.add(role)
        session.commit()
        _grant_permissions(session, role, permissions)
        user.roles.append(role)

    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def _auth_headers(user: User) -> dict[str, str]:
    token = create_access_token(
        user_id=int(user.id),
        email=str(user.email),
        roles=[str(role.name) for role in user.roles],
        org_id=int(user.o_id),
    )
    return {"Authorization": f"Bearer {token}"}


def _create_org(session, name_prefix: str) -> Organisation:
    org = Organisation(name=f"{name_prefix}-{uuid.uuid4().hex[:8]}")
    session.add(org)
    session.commit()
    session.refresh(org)
    return org


def test_login_access_token_contains_org_id(session):
    org = session.query(Organisation).one()
    email = _unique_email("phase1-login")
    password = "phase1-login-pass"
    user = _create_user(session, org_id=int(org.o_id), email=email, password=password)

    with TestClient(app) as client:
        response = client.post(
            "/api/v2/auth/login",
            data={"username": email, "password": password},
        )

    assert response.status_code == 200
    payload = decode_token(response.json()["access_token"])
    assert payload is not None
    assert payload.org_id == int(user.o_id)


def test_access_token_with_wrong_org_claim_is_rejected(session):
    org = session.query(Organisation).one()
    other_org = _create_org(session, "phase1-auth-org")
    user = _create_user(session, org_id=int(org.o_id), email=_unique_email("phase1-auth"))
    bad_token = create_access_token(
        user_id=int(user.id),
        email=str(user.email),
        roles=[],
        org_id=int(other_org.o_id),
    )

    with TestClient(app) as client:
        response = client.get(
            "/api/v2/auth/me",
            headers={"Authorization": f"Bearer {bad_token}"},
        )

    assert response.status_code == 401


def test_users_endpoints_are_org_scoped(session):
    org = session.query(Organisation).one()
    other_org = _create_org(session, "phase1-users-org")
    admin_user = _create_user(
        session,
        org_id=int(org.o_id),
        email=_unique_email("phase1-users-admin"),
        permissions=[PermissionAction.VIEW_USERS, PermissionAction.CREATE_USER],
    )
    other_org_user = _create_user(session, org_id=int(other_org.o_id), email=_unique_email("phase1-users-other"))

    with TestClient(app) as client:
        list_response = client.get("/api/v2/users", headers=_auth_headers(admin_user))
        hidden_response = client.get(f"/api/v2/users/{other_org_user.id}", headers=_auth_headers(admin_user))
        create_response = client.post(
            "/api/v2/users",
            headers=_auth_headers(admin_user),
            json={"email": _unique_email("phase1-created"), "password": "created-pass"},
        )

    assert list_response.status_code == 200
    listed_emails = {item["email"] for item in list_response.json()["users"]}
    assert str(admin_user.email) in listed_emails
    assert str(other_org_user.email) not in listed_emails

    assert hidden_response.status_code == 404
    assert create_response.status_code == 201

    created_email = create_response.json()["user"]["email"]
    created_user = session.query(User).filter(User.email == created_email).one()
    assert int(created_user.o_id) == int(org.o_id)


def test_outcomes_are_org_scoped(session):
    org = session.query(Organisation).one()
    other_org = _create_org(session, "phase1-outcomes-org")
    user = _create_user(
        session,
        org_id=int(org.o_id),
        email=_unique_email("phase1-outcomes-admin"),
        permissions=[PermissionAction.VIEW_OUTCOMES, PermissionAction.CREATE_OUTCOME],
    )
    session.add_all(
        [
            AllowedOutcome(outcome_name="ORG1_ONLY", severity_rank=1, o_id=int(org.o_id)),
            AllowedOutcome(outcome_name="ORG2_ONLY", severity_rank=1, o_id=int(other_org.o_id)),
        ]
    )
    session.commit()

    with TestClient(app) as client:
        list_response = client.get("/api/v2/outcomes", headers=_auth_headers(user))
        create_response = client.post(
            "/api/v2/outcomes",
            headers=_auth_headers(user),
            json={"outcome_name": "phase1_new"},
        )

    assert list_response.status_code == 200
    outcome_names = {item["outcome_name"] for item in list_response.json()["outcomes"]}
    assert "ORG1_ONLY" in outcome_names
    assert "ORG2_ONLY" not in outcome_names

    assert create_response.status_code == 201
    created = session.query(AllowedOutcome).filter(AllowedOutcome.outcome_name == "PHASE1_NEW").one()
    assert int(created.o_id) == int(org.o_id)


def test_user_lists_are_org_scoped(session):
    org = session.query(Organisation).one()
    other_org = _create_org(session, "phase1-lists-org")
    user = _create_user(
        session,
        org_id=int(org.o_id),
        email=_unique_email("phase1-lists-admin"),
        permissions=[PermissionAction.VIEW_LISTS, PermissionAction.CREATE_LIST],
    )
    session.add_all(
        [
            UserList(list_name="Org1List", o_id=int(org.o_id)),
            UserList(list_name="Org2List", o_id=int(other_org.o_id)),
        ]
    )
    session.commit()

    with TestClient(app) as client:
        list_response = client.get("/api/v2/user-lists", headers=_auth_headers(user))
        create_response = client.post(
            "/api/v2/user-lists",
            headers=_auth_headers(user),
            json={"name": "Phase1List"},
        )

    assert list_response.status_code == 200
    list_names = {item["name"] for item in list_response.json()["lists"]}
    assert "Org1List" in list_names
    assert "Org2List" not in list_names

    assert create_response.status_code == 201
    created = session.query(UserList).filter(UserList.list_name == "Phase1List").one()
    assert int(created.o_id) == int(org.o_id)


def test_field_types_and_observations_are_org_scoped(session):
    org = session.query(Organisation).one()
    other_org = _create_org(session, "phase1-field-types-org")
    user = _create_user(
        session,
        org_id=int(org.o_id),
        email=_unique_email("phase1-field-types-admin"),
        permissions=[PermissionAction.VIEW_FIELD_TYPES, PermissionAction.MODIFY_FIELD_TYPES],
    )
    session.add_all(
        [
            FieldTypeConfig(field_name="org1_amount", configured_type="float", o_id=int(org.o_id)),
            FieldTypeConfig(field_name="org2_amount", configured_type="float", o_id=int(other_org.o_id)),
            FieldObservation(field_name="org1_country", observed_json_type="str", o_id=int(org.o_id)),
            FieldObservation(field_name="org2_country", observed_json_type="str", o_id=int(other_org.o_id)),
        ]
    )
    session.commit()

    with TestClient(app) as client:
        config_response = client.get("/api/v2/field-types", headers=_auth_headers(user))
        observation_response = client.get("/api/v2/field-types/observations", headers=_auth_headers(user))
        create_response = client.post(
            "/api/v2/field-types",
            headers=_auth_headers(user),
            json={"field_name": "phase1_score", "configured_type": "integer"},
        )

    assert config_response.status_code == 200
    config_names = {item["field_name"] for item in config_response.json()["configs"]}
    assert "org1_amount" in config_names
    assert "org2_amount" not in config_names

    assert observation_response.status_code == 200
    observation_names = {item["field_name"] for item in observation_response.json()["observations"]}
    assert "org1_country" in observation_names
    assert "org2_country" not in observation_names

    assert create_response.status_code == 201
    created = session.query(FieldTypeConfig).filter(FieldTypeConfig.field_name == "phase1_score").one()
    assert int(created.o_id) == int(org.o_id)


def test_label_usage_and_label_analytics_are_org_scoped(session):
    org = session.query(Organisation).one()
    other_org = _create_org(session, "phase1-labels-org")
    user = _create_user(
        session,
        org_id=int(org.o_id),
        email=_unique_email("phase1-labels-admin"),
        permissions=[PermissionAction.CREATE_LABEL, PermissionAction.VIEW_LABELS],
    )
    label_fraud = Label(label=f"PHASE1_FRAUD_{uuid.uuid4().hex[:6]}", o_id=int(org.o_id))
    label_normal = Label(label=f"PHASE1_NORMAL_{uuid.uuid4().hex[:6]}", o_id=int(org.o_id))
    session.add_all([label_fraud, label_normal])
    session.commit()

    org_event = TestingRecordLog(
        event_id=f"phase1-org-{uuid.uuid4().hex[:6]}",
        event={"amount": 100},
        event_timestamp=1234567890,
        o_id=int(org.o_id),
    )
    org_upload_event = TestingRecordLog(
        event_id=f"phase1-org-upload-{uuid.uuid4().hex[:6]}",
        event={"amount": 200},
        event_timestamp=1234567891,
        o_id=int(org.o_id),
    )
    other_org_event = TestingRecordLog(
        event_id=f"phase1-other-{uuid.uuid4().hex[:6]}",
        event={"amount": 300},
        event_timestamp=1234567892,
        o_id=int(other_org.o_id),
    )
    session.add_all([org_event, org_upload_event, other_org_event])
    session.commit()

    with TestClient(app) as client:
        foreign_mark_response = client.post(
            "/api/v2/labels/mark-event",
            headers=_auth_headers(user),
            json={"event_id": other_org_event.event_id, "label_name": label_fraud.label},
        )
        local_mark_response = client.post(
            "/api/v2/labels/mark-event",
            headers=_auth_headers(user),
            json={"event_id": org_event.event_id, "label_name": label_fraud.label},
        )
        upload_response = client.post(
            "/api/v2/labels/upload",
            headers=_auth_headers(user),
            files={
                "file": (
                    "labels.csv",
                    f"{org_upload_event.event_id},{label_normal.label}\n{other_org_event.event_id},{label_normal.label}\n",
                    "text/csv",
                )
            },
        )
        summary_response = client.get("/api/v2/analytics/labels-summary", headers=_auth_headers(user))
        volume_response = client.get(
            "/api/v2/analytics/labeled-transaction-volume?aggregation=30d",
            headers=_auth_headers(user),
        )

    assert foreign_mark_response.status_code == 404
    assert local_mark_response.status_code == 200

    assert upload_response.status_code == 200
    assert upload_response.json()["successful"] == 1
    assert upload_response.json()["failed"] == 1

    assert summary_response.status_code == 200
    assert summary_response.json()["total_labeled"] == 2

    assert volume_response.status_code == 200
    assert sum(volume_response.json()["data"]) == 2
