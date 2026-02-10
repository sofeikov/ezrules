import pytest
from sqlalchemy.orm import sessionmaker
from sqlalchemy_utils import create_database, database_exists, drop_database

from ezrules.models.backend_core import Organisation, User
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
