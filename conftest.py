import hashlib
import secrets
import uuid

import pytest
from sqlalchemy.orm import sessionmaker
from sqlalchemy_utils import create_database, database_exists, drop_database

from ezrules.models.backend_core import ApiKey, Organisation, User
from ezrules.models.database import Base, engine


@pytest.fixture(scope="session")
def engine_fix():
    if database_exists(engine.url):
        drop_database(engine.url)
    create_database(engine.url)

    Base.metadata.create_all(engine)  # Assuming Base is the declarative base from your models

    yield engine

    # Close all connections before dropping database
    engine.dispose()

    # Try to drop the database, ignore if still in use
    try:
        drop_database(engine.url)
    except Exception:
        # Database might still be in use, which is okay for tests
        pass


@pytest.fixture(scope="session")
def connection(engine_fix):
    connection = engine_fix.connect()
    yield connection
    connection.close()


@pytest.fixture(scope="function")
def session(connection):
    transaction = connection.begin()
    Session = sessionmaker(bind=connection)
    session = Session()

    org = Organisation(name="test_org")
    session.add(org)
    session.commit()

    admin_email = "admin@test_org.com"
    admin_password = "12345678"
    session.add(
        User(
            email=admin_email,
            password=admin_password,
            active=True,
            fs_uniquifier=admin_email,
        )
    )
    session.commit()

    # Set the global db_session to use the test session
    from ezrules.models import database

    database.db_session.registry.clear()
    database.db_session.configure(bind=connection)

    # Set up application context for tests
    from ezrules.core.application_context import reset_context, set_organization_id, set_user_list_manager
    from ezrules.core.user_lists import PersistentUserListManager

    reset_context()  # Reset context between tests
    test_list_provider = PersistentUserListManager(db_session=session, o_id=org.o_id)
    set_organization_id(org.o_id)
    set_user_list_manager(test_list_provider)

    yield session

    # Reset the global db_session
    from ezrules.models import database

    database.db_session.registry.clear()

    # Clean up application context
    reset_context()

    session.close()
    transaction.rollback()


@pytest.fixture(scope="function")
def live_api_key(session):
    """Insert an active API key for the test org and return the raw key string.

    This fixture is available to all test files.  Tests that define their own
    ``live_api_key`` fixture (e.g. test_api_v2_api_keys.py) override this one
    for their own module, so there is no conflict.
    """
    org = session.query(Organisation).first()
    raw_key = "ezrk_" + secrets.token_hex(32)
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    api_key = ApiKey(
        gid=str(uuid.uuid4()),
        key_hash=key_hash,
        label="conftest-test-key",
        o_id=org.o_id,
    )
    session.add(api_key)
    session.commit()
    return raw_key
