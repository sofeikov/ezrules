import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from ezrules.models.backend_core import EventVersionLabel, Label, Organisation, Role, RolesUsers, User
from tests.canonical_helpers import add_served_decision


def _create_org(session, prefix: str) -> Organisation:
    org = Organisation(name=f"{prefix}-{uuid.uuid4().hex[:8]}")
    session.add(org)
    session.commit()
    session.refresh(org)
    return org


def _create_user(session, *, org_id: int, email_prefix: str) -> User:
    user = User(
        email=f"{email_prefix}-{uuid.uuid4().hex[:8]}@example.com",
        password="tenant-hardening-pass",
        active=True,
        fs_uniquifier=str(uuid.uuid4()),
        o_id=org_id,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def test_roles_users_trigger_rejects_cross_org_links(session):
    org = session.query(Organisation).one()
    other_org = _create_org(session, "tenant-hardening-role")
    user = _create_user(session, org_id=int(org.o_id), email_prefix="tenant-hardening-user")
    other_org_role = Role(
        name=f"tenant-hardening-role-{uuid.uuid4().hex[:8]}",
        description="Role in another org",
        o_id=int(other_org.o_id),
    )
    session.add(other_org_role)
    session.commit()

    with pytest.raises(IntegrityError):
        with session.begin_nested():
            session.add(RolesUsers(user_id=int(user.id), role_id=int(other_org_role.id)))
            session.flush()


def test_event_version_label_fk_rejects_cross_org_labels(session):
    org = session.query(Organisation).one()
    other_org = _create_org(session, "tenant-hardening-label")
    decision = add_served_decision(
        session,
        org_id=int(org.o_id),
        event_id=f"tenant-hardening-event-{uuid.uuid4().hex[:8]}",
        event_data={"amount": 42},
        event_timestamp=1_700_000_000,
    )
    other_org_label = Label(label=f"TENANT_HARDENING_{uuid.uuid4().hex[:8]}", o_id=int(other_org.o_id))
    session.add(other_org_label)
    session.commit()

    with pytest.raises(IntegrityError):
        with session.begin_nested():
            session.add(
                EventVersionLabel(
                    o_id=int(org.o_id),
                    ev_id=int(decision.ev_id),
                    el_id=int(other_org_label.el_id),
                )
            )
            session.flush()


def test_event_version_label_fk_rejects_cross_org_event_versions(session):
    org = session.query(Organisation).one()
    other_org = _create_org(session, "tenant-hardening-event-version")
    decision = add_served_decision(
        session,
        org_id=int(org.o_id),
        event_id=f"tenant-hardening-event-version-{uuid.uuid4().hex[:8]}",
        event_data={"amount": 42},
        event_timestamp=1_700_000_000,
    )
    other_org_label = Label(label=f"TENANT_HARDENING_EVENT_{uuid.uuid4().hex[:8]}", o_id=int(other_org.o_id))
    session.add(other_org_label)
    session.commit()

    with pytest.raises(IntegrityError):
        with session.begin_nested():
            session.add(
                EventVersionLabel(
                    o_id=int(other_org.o_id),
                    ev_id=int(decision.ev_id),
                    el_id=int(other_org_label.el_id),
                )
            )
            session.flush()
