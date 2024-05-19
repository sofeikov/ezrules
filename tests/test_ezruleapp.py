import pytest
from backend import ezruleapp
from models.database import engine, Base
from models.backend_core import Organisation, User
from sqlalchemy.orm import sessionmaker
from sqlalchemy_utils import create_database, drop_database, database_exists
from backend.forms import RuleForm


@pytest.fixture(scope="session")
def logged_out_client():
    ezruleapp.app.config["TESTING"] = True
    ezruleapp.app.config["WTF_CSRF_METHODS"] = []

    with ezruleapp.app.test_client() as client:
        yield client


@pytest.fixture(scope="session")
def engine_fix():
    if database_exists(engine.url):
        drop_database(engine.url)
    create_database(engine.url)

    Base.metadata.create_all(
        engine
    )  # Assuming Base is the declarative base from your models

    yield engine

    Base.metadata.drop_all(engine)
    drop_database(engine.url)


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

    admin_email = f"admin@test_org.com"
    admin_password = f"12345678"
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

    yield session

    session.close()
    transaction.rollback()


@pytest.fixture
def logged_in_client(logged_out_client):
    # Log in the test user
    logged_out_client.post(
        "/login",
        data=dict(email="admin@test_org.com", password="12345678"),
        follow_redirects=True,
    )
    yield logged_out_client


def test_can_load_root_page(logged_in_client):
    rv = logged_in_client.get("/", follow_redirects=True)
    assert rv.status_code == 200


def test_can_load_rule_creation(logged_in_client):
    rv = logged_in_client.get("/create_rule")
    rv.status_code == 200


def test_can_create_new_rule(logged_in_client):
    form = RuleForm()
    form.rid.data = "TEST:001"
    form.logic.data = "return 'HOLD'"
    rv = logged_in_client.post("/create_rule", data=form.data, follow_redirects=True)
    assert rv.status_code == 200
