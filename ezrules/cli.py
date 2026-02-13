import logging
import os
import subprocess
import sys
from datetime import datetime, timedelta
from random import choice, choices, randint, uniform
from urllib.parse import urlparse

import bcrypt
import click
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import scoped_session, sessionmaker

from ezrules.backend.data_utils import Event, eval_and_store
from ezrules.backend.rule_executors.executors import LocalRuleExecutorSQL
from ezrules.core.outcomes import DatabaseOutcome
from ezrules.core.permissions import PermissionManager
from ezrules.core.permissions_constants import RoleType
from ezrules.core.rule_updater import (
    RDBRuleEngineConfigProducer,
    RuleManager,
    RuleManagerFactory,
)
from ezrules.core.user_lists import PersistentUserListManager
from ezrules.models.backend_core import Label, Organisation, Role, TestingRecordLog, User
from ezrules.models.backend_core import Rule as RuleModel
from ezrules.models.database import Base, db_session
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
@click.option("--admin", is_flag=True, help="Grant admin role with all permissions to the user")
def add_user(user_email, password, admin):
    db_endpoint = app_settings.DB_ENDPOINT
    engine = create_engine(db_endpoint)
    db_session = scoped_session(sessionmaker(autocommit=False, autoflush=False, bind=engine))
    Base.query = db_session.query_property()

    user = None
    try:
        hashed_password = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        user = User(
            email=user_email,
            password=hashed_password,
            active=True,
            fs_uniquifier=user_email,
        )
        db_session.add(user)
        db_session.commit()
        logger.info(f"Done adding {user_email} to {db_endpoint}")
    except Exception as e:
        db_session.rollback()
        logger.error(e)
        logger.info("User already exists")
        # Try to get existing user
        user = db_session.query(User).filter_by(email=user_email).first()

    try:
        db_session.add(Organisation(name="base"))
        db_session.commit()
    except Exception:
        db_session.rollback()

    # Grant admin permissions if --admin flag is set
    if admin and user:
        logger.info("Granting admin permissions...")

        # Initialize default actions
        PermissionManager.db_session = db_session
        PermissionManager.init_default_actions()

        # Create or get admin role
        admin_role = db_session.query(Role).filter_by(name="admin").first()
        if not admin_role:
            admin_role = Role(name="admin", description="Full system administrator")
            db_session.add(admin_role)
            db_session.commit()
            logger.info("Created admin role")

        # Grant all permissions to admin role
        admin_permissions = RoleType.get_role_permissions(RoleType.ADMIN)
        for permission in admin_permissions:
            try:
                PermissionManager.grant_permission(int(admin_role.id), permission)
            except ValueError:
                logger.warning(f"Permission {permission.value} not found, skipping")

        # Assign admin role to user
        if admin_role not in user.roles:
            user.roles.append(admin_role)
            db_session.commit()
            logger.info(f"Assigned admin role to {user_email}")
        else:
            logger.info(f"User {user_email} already has admin role")

        logger.info(f"User {user_email} now has full admin permissions")


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
        Base.query = db_session.query_property()

        Base.metadata.create_all(bind=engine)

        # Create default organisation
        logger.info("Creating default organisation...")
        existing_org = db_session.query(Organisation).filter_by(name="base").first()
        if not existing_org:
            db_session.add(Organisation(name="base"))
            db_session.commit()
            logger.info("Default organisation created")
        else:
            logger.info("Default organisation already exists")

        # Initialize default permissions
        logger.info("Initializing default permissions...")
        PermissionManager.db_session = db_session
        PermissionManager.init_default_actions()
        logger.info("Default permissions initialized")

        # Seed default outcomes (RELEASE, HOLD, CANCEL)
        logger.info("Seeding default outcomes...")
        outcome_manager = DatabaseOutcome(db_session=db_session, o_id=1)
        outcome_manager._ensure_default_outcomes()
        logger.info("Default outcomes seeded")

        # Seed default user lists (MiddleAsiaCountries, NACountries, LatamCountries)
        logger.info("Seeding default user lists...")
        user_list_manager = PersistentUserListManager(db_session=db_session, o_id=1)
        user_list_manager._ensure_default_lists()
        logger.info("Default user lists seeded")

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
@click.option("--reload", is_flag=True, help="Enable auto-reload for development")
def api(port, reload):
    """Start the FastAPI v2 API server (default port 8888 for Angular frontend)."""
    env = os.environ.copy()
    cmd = [
        "uvicorn",
        "ezrules.backend.api_v2.main:app",
        "--host",
        "0.0.0.0",
        "--port",
        port,
    ]
    if reload:
        cmd.append("--reload")
    subprocess.run(
        cmd,
        env=env,
    )


@cli.command()
@click.option("--n-rules", default=30)
@click.option("--n-events", default=200)
@click.option("--label-ratio", default=0.3, help="Ratio of events to label (0.0-1.0)")
@click.option("--export-csv", help="Export labeled events to CSV file for testing uploads")
def generate_random_data(n_rules: int, n_events: int, label_ratio: float, export_csv: str):
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

    rule_engine_config_producer.save_config(fsrm, changed_by="cli")
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

    # Enhanced labeling logic
    if label_ratio > 0:
        logger.info(f"Labeling {label_ratio * 100:.1f}% of events with realistic patterns...")

        # Get all available labels, create defaults if none exist
        available_labels = {label.label: label for label in db_session.query(Label).all()}
        if not available_labels:
            logger.info("No labels found in database. Creating default labels...")
            _create_default_labels(db_session)
            available_labels = {label.label: label for label in db_session.query(Label).all()}

        if available_labels:
            logger.info(f"Available labels: {list(available_labels.keys())}")

            # Get all generated events
            all_events = db_session.query(TestingRecordLog).filter(TestingRecordLog.event_id.like("TestEvent_%")).all()

            # Determine how many events to label
            n_to_label = int(len(all_events) * label_ratio)
            events_to_label = choices(all_events, k=n_to_label)

            labeled_events = []

            for event_record in events_to_label:
                event_data = event_record.event
                label_name = _determine_realistic_label(event_data, list(available_labels.keys()))

                if label_name and label_name in available_labels:
                    event_record.el_id = available_labels[label_name].el_id
                    labeled_events.append((event_record.event_id, label_name))
                    logger.info(f"Marked {event_record.event_id} as {label_name}")

            db_session.commit()
            logger.info(f"Successfully labeled {len(labeled_events)} events")

            # Export to CSV if requested
            if export_csv and labeled_events:
                _export_labels_to_csv(labeled_events, export_csv)


def _create_default_labels(session):
    """Create default labels in the database"""
    default_labels = ["FRAUD", "CHARGEBACK", "NORMAL"]

    for label_name in default_labels:
        # Check if label already exists to avoid duplicates
        existing = session.query(Label).filter_by(label=label_name).first()
        if not existing:
            label = Label(label=label_name)
            session.add(label)

    session.commit()
    logger.info(f"Created default labels: {default_labels}")


def _determine_realistic_label(event_data: dict, available_labels) -> str | None:
    """Determine a realistic label based on event characteristics"""
    amount = event_data.get("amount", 0)
    score = event_data.get("score", 0)
    is_verified = event_data.get("is_verified", 1)

    # Define realistic labeling patterns
    fraud_probability = 0
    chargeback_probability = 0

    # High amounts are more likely to be scrutinized
    if amount > 800:
        fraud_probability += 0.15
        chargeback_probability += 0.10
    elif amount > 500:
        fraud_probability += 0.08
        chargeback_probability += 0.05

    # High scores indicate suspicion
    if score > 800:
        fraud_probability += 0.25
        chargeback_probability += 0.15
    elif score > 600:
        fraud_probability += 0.12
        chargeback_probability += 0.08

    # Unverified users are riskier
    if is_verified == 0:
        fraud_probability += 0.20
        chargeback_probability += 0.10

    # Determine label based on probabilities
    random_val = uniform(0, 1)

    if "FRAUD" in available_labels and random_val < fraud_probability:
        return "FRAUD"
    elif "CHARGEBACK" in available_labels and random_val < fraud_probability + chargeback_probability:
        return "CHARGEBACK"
    elif "NORMAL" in available_labels and uniform(0, 1) < 0.7:  # 70% of remaining labeled as normal
        return "NORMAL"

    # Default fallback
    return choice(list(available_labels)) if available_labels else None


def _export_labels_to_csv(labeled_events: list, filename: str):
    """Export labeled events to CSV for testing uploads"""
    import csv

    try:
        with open(filename, "w", newline="") as csvfile:
            writer = csv.writer(csvfile)
            for event_id, label_name in labeled_events:
                writer.writerow([event_id, label_name])

        logger.info(f"Exported {len(labeled_events)} labeled events to {filename}")
        logger.info(f"You can now test CSV upload with: Upload Labels -> {filename}")

    except Exception as e:
        logger.error(f"Failed to export CSV: {e}")


@cli.command()
@click.option("--output-file", default="test_labels.csv", help="Output CSV filename")
@click.option("--n-events", default=50, help="Number of events to include in CSV")
@click.option("--unlabeled-only", is_flag=True, help="Only include events that don't have labels yet")
def export_test_csv(output_file: str, n_events: int, unlabeled_only: bool):
    """Export existing events to CSV for testing label uploads"""
    logger.info("Exporting events to CSV for testing...")

    # Get available labels for realistic assignment, create defaults if none exist
    available_labels = [label.label for label in db_session.query(Label).all()]
    if not available_labels:
        logger.info("No labels found in database. Creating default labels...")
        _create_default_labels(db_session)
        available_labels = [label.label for label in db_session.query(Label).all()]

    if not available_labels:
        logger.error("Failed to create labels in database.")
        return

    # Query events based on filter
    query = db_session.query(TestingRecordLog)
    if unlabeled_only:
        query = query.filter(TestingRecordLog.el_id.is_(None))

    events = query.limit(n_events).all()

    if not events:
        logger.warning("No events found matching criteria.")
        return

    # Generate test CSV with realistic labels
    test_labels = []
    for event in events:
        event_data = event.event
        label_name = _determine_realistic_label(event_data, available_labels)
        if label_name:
            test_labels.append((event.event_id, label_name))

    if test_labels:
        _export_labels_to_csv(test_labels, output_file)
        logger.info(f"Generated test CSV with {len(test_labels)} events")
        logger.info("Use this file to test the CSV upload functionality in the web interface")
    else:
        logger.warning("No valid labels could be generated")


@cli.command()
@click.option("--user-email", default="admin@test_org.com", help="Admin email (default: admin@test_org.com)")
@click.option("--password", default="12345678", help="Admin password (default: 12345678)")
@click.option("--n-rules", default=10, help="Number of rules to generate (default: 10)")
@click.option("--n-events", default=1000, help="Number of events to generate (default: 1000)")
@click.pass_context
def reset_dev(ctx, user_email, password, n_rules, n_events):
    """Reset the dev database: init-db --auto-delete + add admin user + generate fake data.

    One command to get a fresh development environment ready to use.
    """
    logger.info("=== Resetting development environment ===")

    # Step 1: init-db --auto-delete
    logger.info("Step 1/3: Initializing database...")
    ctx.invoke(init_db, auto_delete=True)

    # Step 2: add admin user
    logger.info(f"Step 2/3: Creating admin user {user_email}...")
    ctx.invoke(add_user, user_email=user_email, password=password, admin=True)

    # Step 3: generate fake data
    logger.info(f"Step 3/3: Generating fake data ({n_rules} rules, {n_events} events)...")
    ctx.invoke(generate_random_data, n_rules=n_rules, n_events=n_events, label_ratio=0.3, export_csv=None)

    logger.info("=== Development environment ready ===")
    logger.info(f"Login with: {user_email} / {password}")


@cli.command()
def delete_test_data():
    db_session.query(TestingRecordLog).filter(TestingRecordLog.event_id.ilike("TestEvent_%")).delete(
        synchronize_session=False
    )
    db_session.query(RuleModel).filter(RuleModel.rid.ilike("TestRule_%")).delete(synchronize_session=False)
    db_session.commit()


if __name__ == "__main__":
    cli()
