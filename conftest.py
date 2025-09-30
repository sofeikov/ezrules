import pytest
from sqlalchemy.orm import sessionmaker
from sqlalchemy_utils import create_database, database_exists, drop_database

from ezrules.backend import ezruleapp, ezrulevalapp
from ezrules.models.backend_core import Organisation, User
from ezrules.models.database import Base, engine
from ezrules.models.history_meta import versioned_session


@pytest.fixture(scope="function")
def logged_out_manager_client():
    ezruleapp.app.config["TESTING"] = True
    ezruleapp.app.config["WTF_CSRF_METHODS"] = []

    with ezruleapp.app.test_client() as client:
        yield client


@pytest.fixture(scope="function")
def logged_out_eval_client():
    ezrulevalapp.app.config["TESTING"] = True

    with ezrulevalapp.app.test_client() as client:
        yield client


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
    versioned_session(session)

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

    ezruleapp.fsrm.db = session
    ezruleapp.fsrm.o_id = org.o_id
    ezruleapp.rule_engine_config_producer.db = session
    ezruleapp.rule_engine_config_producer.o_id = org.o_id
    ezruleapp.outcome_manager.db_session = session
    ezruleapp.outcome_manager.o_id = org.o_id
    ezruleapp.outcome_manager._initialized = False
    ezruleapp.outcome_manager._cached_outcomes = None
    ezruleapp.user_list_manager.db_session = session
    ezruleapp.user_list_manager.o_id = org.o_id
    ezruleapp.user_list_manager._initialized = False
    ezruleapp.user_list_manager._cached_lists = None
    ezruleapp.label_manager.db_session = session
    ezruleapp.label_manager.o_id = org.o_id
    ezruleapp.label_manager._initialized = False
    ezruleapp.label_manager._cached_labels = None

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
    ezrulevalapp.lre.db = session
    ezrulevalapp.lre.o_id = org.o_id

    yield session

    # Clean up Flask app references to avoid lingering connections
    ezruleapp.fsrm.db = None
    ezruleapp.rule_engine_config_producer.db = None
    ezruleapp.outcome_manager.db_session = None
    ezruleapp.outcome_manager._initialized = False
    ezruleapp.outcome_manager._cached_outcomes = None
    ezruleapp.user_list_manager.db_session = None
    ezruleapp.user_list_manager._initialized = False
    ezruleapp.user_list_manager._cached_lists = None
    ezruleapp.label_manager.db_session = None
    ezruleapp.label_manager._initialized = False
    ezruleapp.label_manager._cached_labels = None

    # Reset the global db_session
    from ezrules.models import database

    database.db_session.registry.clear()

    # Clean up application context
    reset_context()
    ezrulevalapp.lre.db = None

    session.close()
    transaction.rollback()


@pytest.fixture(scope="function")
def logged_in_manager_client(session, logged_out_manager_client):
    # Log in the test user
    logged_out_manager_client.post(
        "/login",
        data=dict(email="admin@test_org.com", password="12345678"),
        follow_redirects=True,
    )
    yield logged_out_manager_client
