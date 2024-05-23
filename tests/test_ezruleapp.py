import pytest
from backend import ezruleapp
from models.database import engine, Base
from models.backend_core import Organisation, User, Rule, RuleHistory
from sqlalchemy.orm import sessionmaker
from sqlalchemy_utils import create_database, drop_database, database_exists
from backend.forms import RuleForm, OutcomeForm
from models.history_meta import versioned_session
from flask import g
import json


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
    versioned_session(session)

    org = Organisation(name="test_org")
    session.add(org)

    admin_email = f"admin@test_org.com"
    admin_password = f"12345678"
    res = session.add(
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

    yield session

    session.close()
    transaction.rollback()


@pytest.fixture
def logged_in_client(session, logged_out_client):
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


def test_can_create_new_rule(session, logged_in_client):
    # Obtain CSRF token from this get request
    logged_in_client.get("/create_rule")

    # Prepare an actual form
    form = RuleForm()
    form.rid.data = "TEST:001"
    form.description.data = "test"
    form.logic.data = "return 'HOLD'"
    form.csrf_token.data = g.csrf_token

    # Post rule and validate it was created
    rv = logged_in_client.post("/create_rule", data=form.data, follow_redirects=True)
    added_rule = session.query(Rule).one()
    assert added_rule.r_id == 1
    assert added_rule.description == "test"
    assert added_rule.rid == "TEST:001"
    assert added_rule.logic == "return 'HOLD'"
    assert rv.status_code == 200


def test_can_not_create_new_invalid_rule(session, logged_in_client):
    # The test is based on not providing a correct csra token thus
    # failing to propvide a valid submit form
    # Prepare an actual form
    form = RuleForm()
    form.rid.data = "TEST:001"
    form.description.data = "test"
    form.logic.data = "return 'NO SUCH OUTCOME'"

    # Post rule and validate it was created
    rv = logged_in_client.post("/create_rule", data=form.data, follow_redirects=True)
    # Still good response as we redirect to the same page
    assert rv.status_code == 200
    assert "Value NO SUCH OUTCOME is not allowed in rule outcome;" in rv.data.decode()
    assert len(session.query(Rule).all()) == 0


def test_cant_display_non_existing_rule(logged_in_client):
    rv = logged_in_client.get("/rule/999", follow_redirects=True)
    assert rv.status_code == 404


def test_can_post_rule_update(session, logged_in_client):
    rule = Rule(
        rid="TEST:001",
        description="test",
        logic="return 'HOLD'",
        o_id=session.query(Organisation).one().o_id,
    )
    session.add(rule)
    session.commit()

    # Obtain CSRF token from this get request
    logged_in_client.get(f"/rule/{rule.r_id}")

    # Prepare an actual form
    form = RuleForm()
    form.rid.data = "TEST:001"
    form.description.data = "test"
    form.logic.data = "return 'CANCEL'"
    form.csrf_token.data = g.csrf_token

    logged_in_client.post(f"/rule/{rule.r_id}", data=form.data, follow_redirects=True)
    logged_in_client.get(f"/rule/{rule.r_id}/1")

    # Make sure history object is created
    assert session.query(RuleHistory).one().version == 1


def test_cant_updat_rule_with_invalid_config(session, logged_in_client):
    rule = Rule(
        rid="TEST:001",
        description="test",
        logic="return 'HOLD'",
        o_id=session.query(Organisation).one().o_id,
    )
    session.add(rule)
    session.commit()

    logged_in_client.get(f"/rule/{rule.r_id}")

    # Prepare an actual form
    form = RuleForm()
    form.rid.data = "TEST:001"
    form.description.data = "test"
    form.logic.data = "return 'NO SUCH OUTCOME'"
    form.csrf_token.data = g.csrf_token

    rv = logged_in_client.post(
        f"/rule/{rule.r_id}", data=form.data, follow_redirects=True
    )
    assert "The rule changes have not been saved, because:" in rv.data.decode()


def test_can_verify_rule_and_extract_params(logged_in_client):
    rv = logged_in_client.post(
        f"/verify_rule",
        json={"rule_source": "if $amount>100:\n\treturn 'HOLD'"},
        follow_redirects=True,
    )
    assert json.loads(rv.data.decode())["params"] == ["amount"]


def test_cant_verify_rule_and_extract_params(logged_in_client):
    rv = logged_in_client.post(
        f"/verify_rule",
        json={"rule_source": "if$amount>100:\n\treturn 'HOLD'"},
        follow_redirects=True,
    )
    assert json.loads(rv.data.decode()) == {}


def test_ping(logged_in_client):
    rv = logged_in_client.get(f"/ping")
    assert rv.data.decode() == "OK"


def test_can_load_user_lists(logged_in_client):
    rv = logged_in_client.get(f"/management/lists")
    assert rv.status_code == 200


def test_can_load_outcomes_page(logged_in_client):
    rv = logged_in_client.get(f"/management/outcomes")
    assert rv.status_code == 200


def test_can_add_outcomes(logged_in_client):
    logged_in_client.get(f"/management/outcomes")

    form = OutcomeForm()
    form.outcome.data = "NEW_TEST_OUTCOME"
    form.csrf_token.data = g.csrf_token

    rv = logged_in_client.post(
        f"/management/outcomes", data=form.data, follow_redirects=True
    )
    assert "NEW_TEST_OUTCOME" in ezruleapp.outcome_manager.get_allowed_outcomes()
    assert rv.status_code == 200


@pytest.mark.parametrize(
    ["rule_source", "expected_response", "test_json"],
    [
        (
            "if $amount > 100:\n\treturn 'HOLD'",
            {"reason": "ok", "rule_outcome": "HOLD", "status": "ok"},
            json.dumps({"amount": 900}),
        ),
        (
            "if $amount > 100:\n\treturn 'HOLD'",
            {
                "status": "error",
                "reason": "Example is malformed",
                "rule_outcome": None,
            },
            f"\INCORRECT JSON",
        ),
        (
            "if $amount > 100\n\treturn 'HOLD'",
            {
                "status": "error",
                "reason": "Rule source is invalid",
                "rule_outcome": None,
            },
            json.dumps({"amount": 900}),
        ),
    ],
)
def test_can_test_rule(logged_in_client, rule_source, expected_response, test_json):
    rv = logged_in_client.post(
        f"/test_rule",
        json={
            "rule_source": rule_source,
            "test_json": test_json,
        },
        follow_redirects=True,
    )
    test_result = json.loads(rv.data.decode())
    assert test_result == expected_response


def test_can_load_timeline(session, logged_in_client):
    rule = Rule(
        rid="TEST:001",
        description="test",
        logic="return 'HOLD'",
        o_id=session.query(Organisation).one().o_id,
    )
    session.add(rule)
    session.commit()

    # Make changes
    rule.description = "update"
    session.commit()

    rv = logged_in_client.get(f"/rule/{rule.r_id}/timeline")
    rv.status_code == 200
