import csv
import logging
import os
import subprocess
import sys
from pathlib import Path
from random import Random
from urllib.parse import urlparse

import bcrypt
import click
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import scoped_session, sessionmaker

from ezrules.backend.data_utils import Event, eval_and_store
from ezrules.backend.rule_executors.executors import LocalRuleExecutorSQL
from ezrules.backend.utils import record_observations
from ezrules.core.application_context import set_organization_id, set_user_list_manager
from ezrules.core.outcomes import DatabaseOutcome
from ezrules.core.permissions import PermissionManager
from ezrules.core.permissions_constants import RoleType
from ezrules.core.rule_updater import (
    RDBRuleEngineConfigProducer,
    RuleManager,
    RuleManagerFactory,
)
from ezrules.core.user_lists import PersistentUserListManager
from ezrules.demo_data import build_demo_events, build_demo_rules, determine_demo_label, seed_demo_user_lists
from ezrules.models.backend_core import (
    AllowedOutcome,
    Label,
    Organisation,
    Role,
    RuleQualityPair,
    TestingRecordLog,
    User,
)
from ezrules.models.backend_core import Rule as RuleModel
from ezrules.models.database import Base, db_session
from ezrules.settings import app_settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DEMO_DATA_COMMIT_BATCH_SIZE = 50
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RESET_DEV_LABELS_CSV_PATH = PROJECT_ROOT / "test_labels.csv"


def _get_or_create_default_organisation(db_session):
    """Return the default organisation, creating it when needed."""
    organisation = db_session.query(Organisation).filter_by(name="base").first()
    if organisation is None:
        organisation = Organisation(name="base")
        db_session.add(organisation)
        db_session.commit()
        db_session.refresh(organisation)
    return organisation


def _get_or_create_role(
    session,
    *,
    o_id: int,
    name: str,
    description: str,
) -> Role:
    """Return an organization-scoped role, creating it when needed."""
    role = session.query(Role).filter(Role.o_id == o_id, Role.name == name).first()
    if role is None:
        role = Role(name=name, description=description, o_id=o_id)
        session.add(role)
        session.commit()
    elif description and role.description != description:
        role.description = description
        session.commit()
    return role


def _ensure_default_roles(session, *, o_id: int) -> dict[str, Role]:
    """Ensure the standard system roles exist for the given organization."""
    PermissionManager.db_session = session
    PermissionManager.init_default_actions()

    role_specs = {
        RoleType.ADMIN: ("admin", "Full system administrator"),
        RoleType.READONLY: ("readonly", "Read-only access"),
        RoleType.RULE_EDITOR: ("rule_editor", "Can create and modify rules"),
    }
    roles: dict[str, Role] = {}

    for role_type, (name, description) in role_specs.items():
        role = _get_or_create_role(session, o_id=o_id, name=name, description=description)
        for permission in RoleType.get_role_permissions(role_type):
            try:
                PermissionManager.grant_permission(int(role.id), permission)
            except ValueError:
                logger.warning("Permission %s not found, skipping", permission.value)
        roles[name] = role

    return roles


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


def _upgrade_database_schema(db_endpoint: str) -> None:
    """Apply all pending database migrations for the configured database."""
    logger.info("Applying database migrations with Alembic...")
    env = os.environ.copy()
    env["EZRULES_DB_ENDPOINT"] = db_endpoint
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        error_text = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"Alembic migration failed: {error_text}")


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
        organisation = _get_or_create_default_organisation(db_session)
        hashed_password = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        user = User(
            email=user_email,
            password=hashed_password,
            active=True,
            fs_uniquifier=user_email,
            o_id=int(organisation.o_id),
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
        _get_or_create_default_organisation(db_session)

        # Grant admin permissions if --admin flag is set
    if admin and user:
        logger.info("Granting admin permissions...")

        admin_role = _ensure_default_roles(db_session, o_id=int(user.o_id))["admin"]

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

    # Now apply migrations and seed default data
    try:
        _upgrade_database_schema(db_endpoint)

        engine = create_engine(db_endpoint)
        db_session = scoped_session(sessionmaker(autocommit=False, autoflush=False, bind=engine))
        Base.query = db_session.query_property()

        # Create default organisation
        logger.info("Creating default organisation...")
        existing_org = _get_or_create_default_organisation(db_session)
        logger.info("Default organisation ready: %s", existing_org.name)

        # Initialize default permissions
        logger.info("Initializing default permissions...")
        PermissionManager.db_session = db_session
        PermissionManager.init_default_actions()
        logger.info("Default permissions initialized")

        logger.info("Seeding default roles...")
        _ensure_default_roles(db_session, o_id=int(existing_org.o_id))
        logger.info("Default roles seeded")

        # Seed default outcomes (RELEASE, HOLD, CANCEL)
        logger.info("Seeding default outcomes...")
        outcome_manager = DatabaseOutcome(db_session=db_session, o_id=int(existing_org.o_id))
        outcome_manager._ensure_default_outcomes()
        logger.info("Default outcomes seeded")

        # Seed default user lists (MiddleAsiaCountries, NACountries, LatamCountries)
        logger.info("Seeding default user lists...")
        user_list_manager = PersistentUserListManager(db_session=db_session, o_id=int(existing_org.o_id))
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

    organisation = _get_or_create_default_organisation(db_session)
    _ensure_default_roles(db_session, o_id=int(organisation.o_id))

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
    if n_rules < 0 or n_events < 0:
        raise click.BadParameter("n-rules and n-events must be zero or greater")
    if not 0 <= label_ratio <= 1:
        raise click.BadParameter("label-ratio must be between 0.0 and 1.0")

    organisation = _get_or_create_default_organisation(db_session)
    org_id = int(organisation.o_id)
    rng = Random()
    user_list_manager = PersistentUserListManager(db_session=db_session, o_id=org_id)
    set_user_list_manager(user_list_manager)
    set_organization_id(org_id)
    seed_demo_user_lists(user_list_manager)

    fsrm: RuleManager = RuleManagerFactory.get_rule_manager("RDBRuleManager", **{"db": db_session, "o_id": org_id})
    rule_engine_config_producer = RDBRuleEngineConfigProducer(db=db_session, o_id=org_id)
    existing_rule_count = (
        db_session.query(RuleModel)
        .filter(
            RuleModel.o_id == org_id,
            RuleModel.rid.like("TestRule_%"),
        )
        .count()
    )
    generated_rules = build_demo_rules(n_rules=n_rules, start_index=existing_rule_count)
    for rule in generated_rules:
        db_session.add(RuleModel(rid=rule.rid, logic=rule.logic, description=rule.description, o_id=org_id))
    if generated_rules:
        db_session.commit()
        logger.info(
            "Generated %s fraud-demo rules with list-backed conditions and correlated thresholds.", len(generated_rules)
        )

    rule_engine_config_producer.save_config(fsrm, changed_by="cli")
    lre = LocalRuleExecutorSQL(db=db_session, o_id=org_id)

    # Generate and evaluate events
    existing_event_count = (
        db_session.query(TestingRecordLog)
        .filter(
            TestingRecordLog.o_id == org_id,
            TestingRecordLog.event_id.like("TestEvent_%"),
        )
        .count()
    )
    generated_events = build_demo_events(n_events=n_events, start_index=existing_event_count)
    for index, generated_event in enumerate(generated_events, start=1):
        event = Event(
            event_id=generated_event.event_id,
            event_timestamp=generated_event.event_timestamp,
            event_data=generated_event.event_data,
        )

        # Evaluate the event against the rules and store the results
        response = eval_and_store(lre, event, commit=False)
        record_observations(db_session, generated_event.event_data, org_id, commit=False)
        if index % DEMO_DATA_COMMIT_BATCH_SIZE == 0:
            db_session.commit()
        if index == n_events or index % 25 == 0:
            logger.info(
                "Evaluated %s/%s demo events. Last outcome set: %s", index, n_events, response[0]["outcome_set"]
            )
    if generated_events:
        db_session.commit()

    # Enhanced labeling logic
    if label_ratio > 0 and generated_events:
        logger.info(f"Labeling {label_ratio * 100:.1f}% of events with realistic patterns...")

        # Get all available labels, create defaults if none exist
        available_labels = {label.label: label for label in db_session.query(Label).filter(Label.o_id == org_id).all()}
        if not available_labels:
            logger.info("No labels found in database. Creating default labels...")
            _create_default_labels(db_session, o_id=org_id)
            available_labels = {
                label.label: label for label in db_session.query(Label).filter(Label.o_id == org_id).all()
            }

        if available_labels:
            logger.info(f"Available labels: {list(available_labels.keys())}")

            generated_event_ids = [generated_event.event_id for generated_event in generated_events]
            all_events = (
                db_session.query(TestingRecordLog)
                .filter(
                    TestingRecordLog.o_id == org_id,
                    TestingRecordLog.event_id.in_(generated_event_ids),
                )
                .all()
            )

            # Determine how many events to label
            n_to_label = int(len(all_events) * label_ratio)
            if n_to_label <= 0:
                events_to_label = []
            elif n_to_label >= len(all_events):
                events_to_label = all_events
            else:
                events_to_label = rng.sample(all_events, k=n_to_label)

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


def _create_default_labels(session, *, o_id: int):
    """Create default labels in the database"""
    default_labels = ["FRAUD", "CHARGEBACK", "NORMAL"]

    for label_name in default_labels:
        # Check if label already exists to avoid duplicates
        existing = session.query(Label).filter(Label.o_id == o_id, Label.label == label_name).first()
        if not existing:
            label = Label(label=label_name, o_id=o_id)
            session.add(label)

    session.commit()
    logger.info(f"Created default labels: {default_labels}")


def _determine_realistic_label(event_data: dict, available_labels) -> str | None:
    """Determine a realistic label based on event characteristics"""
    return determine_demo_label(event_data, list(available_labels))


def _ensure_rule_quality_pair(
    session,
    *,
    o_id: int,
    outcome: str,
    label: str,
    created_by: str,
) -> bool:
    normalized_outcome = outcome.strip()
    normalized_label = label.strip()

    outcome_exists = (
        session.query(AllowedOutcome)
        .filter(AllowedOutcome.o_id == o_id, AllowedOutcome.outcome_name == normalized_outcome)
        .first()
        is not None
    )
    label_exists = (
        session.query(Label)
        .filter(
            Label.o_id == o_id,
            Label.label == normalized_label,
        )
        .first()
        is not None
    )
    if not outcome_exists or not label_exists:
        logger.warning(
            "Skipping default rule-quality pair %s -> %s because the outcome or label is missing.",
            normalized_outcome,
            normalized_label,
        )
        return False

    pair = (
        session.query(RuleQualityPair)
        .filter(
            RuleQualityPair.o_id == o_id,
            RuleQualityPair.outcome == normalized_outcome,
            RuleQualityPair.label == normalized_label,
        )
        .first()
    )
    if pair is not None:
        if not pair.active:
            pair.active = True
            session.commit()
            logger.info("Reactivated default rule-quality pair %s -> %s", normalized_outcome, normalized_label)
        else:
            logger.info("Default rule-quality pair %s -> %s already present", normalized_outcome, normalized_label)
        return True

    session.add(
        RuleQualityPair(
            outcome=normalized_outcome,
            label=normalized_label,
            active=True,
            created_by=created_by,
            o_id=o_id,
        )
    )
    session.commit()
    logger.info("Seeded default rule-quality pair %s -> %s", normalized_outcome, normalized_label)
    return True


DEFAULT_DEMO_RULE_QUALITY_PAIRS = (
    ("RELEASE", "CHARGEBACK"),
    ("HOLD", "CHARGEBACK"),
    ("CANCEL", "FRAUD"),
)


def _ensure_default_rule_quality_pairs(
    session,
    *,
    o_id: int,
    created_by: str,
) -> list[tuple[str, str]]:
    seeded_pairs: list[tuple[str, str]] = []
    for outcome, label in DEFAULT_DEMO_RULE_QUALITY_PAIRS:
        if _ensure_rule_quality_pair(
            session,
            o_id=o_id,
            outcome=outcome,
            label=label,
            created_by=created_by,
        ):
            seeded_pairs.append((outcome, label))
    return seeded_pairs


def _export_labels_to_csv(labeled_events: list, filename: str):
    """Export labeled events to CSV for testing uploads"""
    try:
        with open(filename, "w", newline="") as csvfile:
            writer = csv.writer(csvfile)
            for event_id, label_name in labeled_events:
                writer.writerow([event_id, label_name])

        logger.info(f"Exported {len(labeled_events)} labeled events to {filename}")
        logger.info(f"You can now test CSV upload with: Upload Labels -> {filename}")

    except Exception as e:
        logger.error(f"Failed to export CSV: {e}")


def _invoke_reset_dev_generation(ctx, *, n_rules: int, n_events: int) -> None:
    ctx.invoke(
        generate_random_data,
        n_rules=n_rules,
        n_events=n_events,
        label_ratio=0.3,
        export_csv=str(DEFAULT_RESET_DEV_LABELS_CSV_PATH),
    )


@cli.command()
@click.option("--output-file", default="test_labels.csv", help="Output CSV filename")
@click.option("--n-events", default=50, help="Number of events to include in CSV")
@click.option("--unlabeled-only", is_flag=True, help="Only include events that don't have labels yet")
def export_test_csv(output_file: str, n_events: int, unlabeled_only: bool):
    """Export existing events to CSV for testing label uploads"""
    logger.info("Exporting events to CSV for testing...")
    organisation = _get_or_create_default_organisation(db_session)
    org_id = int(organisation.o_id)

    # Get available labels for realistic assignment, create defaults if none exist
    available_labels = [label.label for label in db_session.query(Label).filter(Label.o_id == org_id).all()]
    if not available_labels:
        logger.info("No labels found in database. Creating default labels...")
        _create_default_labels(db_session, o_id=org_id)
        available_labels = [label.label for label in db_session.query(Label).filter(Label.o_id == org_id).all()]

    if not available_labels:
        logger.error("Failed to create labels in database.")
        return

    # Query events based on filter
    query = db_session.query(TestingRecordLog).filter(TestingRecordLog.o_id == org_id)
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
    _invoke_reset_dev_generation(ctx, n_rules=n_rules, n_events=n_events)
    _ensure_default_rule_quality_pairs(
        db_session,
        o_id=int(_get_or_create_default_organisation(db_session).o_id),
        created_by="cli.reset_dev",
    )

    logger.info("=== Development environment ready ===")
    logger.info("Generated label-upload CSV at: %s", DEFAULT_RESET_DEV_LABELS_CSV_PATH)
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
