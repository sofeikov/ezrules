import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from ezrules.models.backend_core import Label, Organisation, Role, RolesUsers, TestingRecordLog, User


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


def test_testing_record_log_label_fk_rejects_cross_org_labels(session):
    org = session.query(Organisation).one()
    other_org = _create_org(session, "tenant-hardening-label")
    event = TestingRecordLog(
        event_id=f"tenant-hardening-event-{uuid.uuid4().hex[:8]}",
        event={"amount": 42},
        event_timestamp=1_700_000_000,
        o_id=int(org.o_id),
    )
    other_org_label = Label(label=f"TENANT_HARDENING_{uuid.uuid4().hex[:8]}", o_id=int(other_org.o_id))
    session.add_all([event, other_org_label])
    session.commit()

    with pytest.raises(IntegrityError):
        with session.begin_nested():
            event.el_id = int(other_org_label.el_id)
            session.flush()
