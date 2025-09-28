import logging
import os
import subprocess
import sys
from datetime import datetime, timedelta
from random import choice, choices, randint, uniform
from urllib.parse import urlparse

import click
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import scoped_session, sessionmaker

from ezrules.backend.data_utils import Event, eval_and_store
from ezrules.backend.rule_executors.executors import LocalRuleExecutorSQL
from ezrules.core.permissions import PermissionManager
from ezrules.core.permissions_constants import RoleType
from ezrules.core.rule_updater import (
    RDBRuleEngineConfigProducer,
    RuleManager,
    RuleManagerFactory,
)
from ezrules.models.backend_core import Organisation, Role, TestingRecordLog, User
from ezrules.models.backend_core import Rule as RuleModel
from ezrules.models.database import Base, db_session
from ezrules.models.history_meta import versioned_session
from ezrules.settings import app_settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _drop_database(engine, db_name):
    """Drop the specified database."""
    logger.info(f"Dropping database '{db_name}'...")
    with engine.connect() as conn:
        conn.execute(text("COMMIT"))  # End any transaction
        # Terminate all connections to the database before dropping
        conn.execute(
            text("""
            SELECT pg_terminate_backend(pid)
            FROM pg_stat_activity
            WHERE datname = :db_name AND pid <> pg_backend_pid()
        """),
            {"db_name": db_name},
        )
        conn.execute(text(f"DROP DATABASE IF EXISTS {db_name}"))
    logger.info(f"Database '{db_name}' dropped successfully")


def _create_database(engine, db_name):
    """Create the specified database if it doesn't exist."""
    logger.info(f"Creating database '{db_name}'...")
    with engine.connect() as conn:
        conn.execute(text("COMMIT"))  # End any transaction
        # Check if database exists before creating
        result = conn.execute(text("SELECT 1 FROM pg_database WHERE datname = :db_name"), {"db_name": db_name})
        if result.fetchone() is None:
            conn.execute(text(f"CREATE DATABASE {db_name}"))
            logger.info(f"Database '{db_name}' created successfully")
        else:
            logger.info(f"Database '{db_name}' already exists")


@click.group()
def cli():
    pass


@cli.command()
@click.option("--user-email")
@click.option("--password")
def add_user(user_email, password):
    db_endpoint = app_settings.DB_ENDPOINT
    engine = create_engine(db_endpoint)
    db_session = scoped_session(sessionmaker(autocommit=False, autoflush=False, bind=engine))
    versioned_session(db_session)

    try:
        db_session.add(
            User(
                email=user_email,
                password=password,
                active=True,
                fs_uniquifier=user_email,
            )
        )
        db_session.commit()
        logger.info(f"Done adding {user_email} to {db_endpoint}")
    except Exception:
        db_session.rollback()
        logger.info("User already exists")
    try:
        db_session.add(Organisation(name="base"))
        db_session.commit()
    except Exception:
        db_session.rollback()


@cli.command()
@click.option("--auto-delete", is_flag=True, help="Automatically delete existing database without prompting")
def init_db(auto_delete):
    db_endpoint = app_settings.DB_ENDPOINT
    logger.info(f"Initializing the DB at {db_endpoint}")

    # Parse the database URL to get database name
    parsed_url = urlparse(db_endpoint)
    db_name = parsed_url.path.lstrip("/")

    # Create connection URL without database name for checking existence
    if parsed_url.username and parsed_url.password:
        base_url = (
            f"{parsed_url.scheme}://{parsed_url.username}:{parsed_url.password}@{parsed_url.hostname}:{parsed_url.port}"
        )
    else:
        base_url = f"{parsed_url.scheme}://{parsed_url.hostname}:{parsed_url.port}"

    # Check if database exists
    try:
        base_engine = create_engine(base_url + "/postgres")  # Connect to default postgres db
        with base_engine.connect() as conn:
            conn.execute(text("COMMIT"))  # End any transaction
            result = conn.execute(text("SELECT 1 FROM pg_database WHERE datname = :db_name"), {"db_name": db_name})
            db_exists = result.fetchone() is not None

        if db_exists:
            if auto_delete:
                logger.info(f"Database '{db_name}' exists. Auto-deleting...")
                _drop_database(base_engine, db_name)
            else:
                response = click.prompt(
                    f"Database '{db_name}' already exists. Do you want to delete it and recreate? (y/N)",
                    default="N",
                    type=str,
                )
                if response.lower() in ["y", "yes"]:
                    _drop_database(base_engine, db_name)
                else:
                    logger.info("Database initialization cancelled.")
                    sys.exit(0)

        # Create database if it doesn't exist
        _create_database(base_engine, db_name)
        base_engine.dispose()

    except OperationalError as e:
        logger.error(f"Failed to connect to database server: {e}")
        sys.exit(1)

    # Now initialize the database schema and permissions
    try:
        engine = create_engine(db_endpoint)
        db_session = scoped_session(sessionmaker(autocommit=False, autoflush=False, bind=engine))
        versioned_session(db_session)
        Base.query = db_session.query_property()

        Base.metadata.create_all(bind=engine)

        # Initialize default permissions
        logger.info("Initializing default permissions...")
        PermissionManager.db_session = db_session
        PermissionManager.init_default_actions()
        logger.info("Default permissions initialized")

        logger.info(f"Done initializing the DB at {db_endpoint}")

    except Exception as e:
        logger.error(f"Failed to initialize database schema: {e}")
        sys.exit(1)


@cli.command()
def init_permissions():
    db_endpoint = app_settings.DB_ENDPOINT
    logger.info(f"Initializing permissions at {db_endpoint}")
    engine = create_engine(db_endpoint)
    db_session = scoped_session(sessionmaker(autocommit=False, autoflush=False, bind=engine))
    versioned_session(db_session)
    Base.query = db_session.query_property()

    PermissionManager.init_default_actions()

    admin_role = db_session.query(Role).filter_by(name="admin").first()
    if not admin_role:
        admin_role = Role(name="admin", description="Full system administrator")
        db_session.add(admin_role)
        db_session.commit()

    readonly_role = db_session.query(Role).filter_by(name="readonly").first()
    if not readonly_role:
        readonly_role = Role(name="readonly", description="Read-only access")
        db_session.add(readonly_role)
        db_session.commit()

    rule_editor_role = db_session.query(Role).filter_by(name="rule_editor").first()
    if not rule_editor_role:
        rule_editor_role = Role(name="rule_editor", description="Can create and modify rules")
        db_session.add(rule_editor_role)
        db_session.commit()

    # Get permissions for each role type using the enum
    admin_permissions = RoleType.get_role_permissions(RoleType.ADMIN)
    readonly_permissions = RoleType.get_role_permissions(RoleType.READONLY)
    rule_editor_permissions = RoleType.get_role_permissions(RoleType.RULE_EDITOR)

    for permission in admin_permissions:
        try:
            PermissionManager.grant_permission(int(admin_role.id), permission)
        except ValueError:
            logger.warning(f"Permission {permission.value} not found, skipping")

    for permission in readonly_permissions:
        try:
            PermissionManager.grant_permission(int(readonly_role.id), permission)
        except ValueError:
            logger.warning(f"Permission {permission.value} not found, skipping")

    for permission in rule_editor_permissions:
        try:
            PermissionManager.grant_permission(int(rule_editor_role.id), permission)
        except ValueError:
            logger.warning(f"Permission {permission.value} not found, skipping")

    logger.info("Permissions initialized successfully")


@cli.command()
@click.option("--port", default="8888")
def manager(port):
    env = os.environ.copy()
    cmd = [
        "gunicorn",
        "-w",
        "1",
        "--threads",
        "4",
        "--bind",
        f"0.0.0.0:{port}",
        "ezrules.backend.ezruleapp:app",
    ]
    subprocess.run(
        cmd,
        env=env,
    )


@cli.command()
@click.option("--port", default="9999")
def evaluator(port):
    env = os.environ.copy()
    cmd = [
        "gunicorn",
        "-w",
        "1",
        "--threads",
        "4",
        "--bind",
        f"0.0.0.0:{port}",
        "ezrules.backend.ezrulevalapp:app",
    ]
    subprocess.run(
        cmd,
        env=env,
    )


@cli.command()
@click.option("--n-rules", default=30)
@click.option("--n-events", default=200)
def generate_random_data(n_rules: int, n_events: int):
    test_attributes = {
        "amount": float,
        "send_country": str,
        "receive_country": str,
        "score": float,
        "is_verified": int,
    }
    fsrm: RuleManager = RuleManagerFactory.get_rule_manager("RDBRuleManager", **{"db": db_session, "o_id": 1})
    rule_engine_config_producer = RDBRuleEngineConfigProducer(db=db_session, o_id=1)
    all_attrs = list(test_attributes)
    for r_ind in range(n_rules):
        n_attrs_by_rule = randint(1, len(all_attrs))
        selected_attrs = set(choices(all_attrs, k=n_attrs_by_rule))

        # Logic is a simple "if" statement randomly combining the attributes above with some thresholds
        conditions = []
        for attr in selected_attrs:
            if test_attributes[attr] is float:
                threshold = round(uniform(0, 1000), 2)
                conditions.append(f"${attr} > {threshold}")
            elif test_attributes[attr] is str:
                value = f"'{attr}_value_{randint(1, 10)}'"
                conditions.append(f"${attr} == {value}")
            elif test_attributes[attr] is int:
                threshold = randint(0, 1)
                conditions.append(f"${attr} == {threshold}")

        logic = " and ".join(conditions)
        outcome = choice(["HOLD", "CANCEL", "RELEASE"])
        logic = f"if {logic}:\n    return '{outcome}'"

        # Create a description for the rule
        description = f"This rule applies when: {', '.join(conditions)}."

        # Create the RuleModel instance
        r = RuleModel(rid=f"TestRule_Rule_{r_ind}", logic=logic, description=description, o_id=1)

        # Add the rule to the database session and commit it
        db_session.add(r)
        db_session.commit()

        print(f"Generated Rule {r_ind}: {logic}")

        lre = LocalRuleExecutorSQL(db=db_session, o_id=1)

    rule_engine_config_producer.save_config(fsrm)
    # Generate and evaluate events
    for e_ind in range(n_events):
        event_data = {}
        for attr, attr_type in test_attributes.items():
            if attr_type is float:
                event_data[attr] = round(uniform(0, 1000), 2)
            elif attr_type is str:
                event_data[attr] = f"{attr}_value_{randint(1, 10)}"
            elif attr_type is int:
                event_data[attr] = randint(0, 1)

        # Calculate a timestamp within the last month
        current_time = datetime.now()
        start_time = current_time - timedelta(days=30)
        event_timestamp = randint(int(start_time.timestamp()), int(current_time.timestamp()))

        event = Event(
            event_id=f"TestEvent_Event_{e_ind}",
            event_timestamp=event_timestamp,
            event_data=event_data,
        )

        # Evaluate the event against the rules and store the results
        response = eval_and_store(lre, event)
        print(f"Evaluated Event {e_ind}: {response}")

    cb = db_session.query(Label).where(Label.label == "CHARGEBACK").one()
    for trl in db_session.query(TestingRecordLog).all():
        if uniform(0, 100) < 10:
            print(f"Marking {trl.event_id} as CHARGEBACK")
            trl.el_id = cb.el_id
    db_session.commit()


@cli.command()
def delete_test_data():
    db_session.query(TestingRecordLog).filter(TestingRecordLog.event_id.ilike("TestEvent_%")).delete(
        synchronize_session=False
    )
    db_session.query(RuleModel).filter(RuleModel.rid.ilike("TestRule_%")).delete(synchronize_session=False)
    db_session.commit()


if __name__ == "__main__":
    cli()
