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
from ezrules.backend.label_assignments import assign_event_version_label, get_labelable_event_version
from ezrules.backend.rule_executors.executors import LocalRuleExecutorSQL
from ezrules.backend.utils import record_observations
from ezrules.core.application_context import set_organization_id, set_user_list_manager
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
    EventVersionLabel,
    Label,
    Organisation,
    Role,
    RuleQualityPair,
    TestingRecordLog,
    User,
)
from ezrules.models.backend_core import Rule as RuleModel
from ezrules.models.database import Base
from ezrules.settings import app_settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DEMO_DATA_COMMIT_BATCH_SIZE = 50
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RESET_DEV_LABELS_CSV_PATH = PROJECT_ROOT / "test_labels.csv"
DEFAULT_RESET_DEV_OUTCOMES = ("CANCEL", "HOLD", "RELEASE")
DEFAULT_RESET_DEV_LABELS = ("FRAUD", "CHARGEBACK", "NORMAL")


def _create_cli_session():
    db_endpoint = app_settings.DB_ENDPOINT
    engine = create_engine(db_endpoint)
    session = scoped_session(sessionmaker(autocommit=False, autoflush=False, bind=engine))
    Base.query = session.query_property()
    return db_endpoint, engine, session


def _close_cli_session(engine, session) -> None:
    session.remove()
    engine.dispose()


def _normalize_organisation_name(org_name: str) -> str:
    normalized = org_name.strip()
    if not normalized:
        raise click.BadParameter("Organisation name cannot be empty")
    return normalized


def _normalize_user_email(user_email: str) -> str:
    normalized = user_email.strip()
    if not normalized:
        raise click.BadParameter("User email cannot be empty")
    return normalized


def _get_organisation_by_name(session, *, org_name: str) -> Organisation | None:
    normalized_name = _normalize_organisation_name(org_name)
    return session.query(Organisation).filter(Organisation.name == normalized_name).first()


def _create_organisation(session, *, org_name: str) -> Organisation:
    organization = Organisation(name=_normalize_organisation_name(org_name))
    session.add(organization)
    session.commit()
    session.refresh(organization)
    return organization


def _get_or_create_organisation(session, *, org_name: str) -> tuple[Organisation, bool]:
    organization = _get_organisation_by_name(session, org_name=org_name)
    if organization is not None:
        return organization, False
    return _create_organisation(session, org_name=org_name), True


def _resolve_organisation(session, *, org_name: str | None = None) -> Organisation:
    if org_name is not None:
        organization = _get_organisation_by_name(session, org_name=org_name)
        if organization is None:
            raise click.ClickException(
                f"Organisation '{_normalize_organisation_name(org_name)}' does not exist. "
                "Run `uv run ezrules bootstrap-org --name <org-name> ...` first."
            )
        return organization

    organisations = session.query(Organisation).order_by(Organisation.name).all()
    if len(organisations) == 1:
        return organisations[0]
    if not organisations:
        raise click.ClickException(
            "No organisation exists. Run `uv run ezrules bootstrap-org --name <org-name> ...` first."
        )

    available_orgs = ", ".join(str(org.name) for org in organisations)
    raise click.ClickException(
        f"Multiple organisations exist. Pass --org-name to select one. Available organisations: {available_orgs}"
    )


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _create_user(session, *, user_email: str, password: str, org_id: int) -> User:
    normalized_email = _normalize_user_email(user_email)
    existing_user = session.query(User).filter(User.email == normalized_email).first()
    if existing_user is not None:
        existing_user_org_id = int(existing_user.o_id)
        if existing_user_org_id == org_id:
            raise click.ClickException(f"User '{normalized_email}' already exists in the selected organisation.")

        existing_org = session.query(Organisation).filter(Organisation.o_id == existing_user_org_id).first()
        existing_org_name = str(existing_org.name) if existing_org is not None else f"o_id={existing_user_org_id}"
        raise click.ClickException(f"User '{normalized_email}' already exists in organisation '{existing_org_name}'.")

    user = User(
        email=normalized_email,
        password=_hash_password(password),
        active=True,
        fs_uniquifier=normalized_email,
        o_id=org_id,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def _get_or_create_user(session, *, user_email: str, password: str, org_id: int) -> tuple[User, bool]:
    normalized_email = _normalize_user_email(user_email)
    existing_user = session.query(User).filter(User.email == normalized_email).first()
    if existing_user is not None:
        existing_user_org_id = int(existing_user.o_id)
        if existing_user_org_id != org_id:
            existing_org = session.query(Organisation).filter(Organisation.o_id == existing_user_org_id).first()
            existing_org_name = str(existing_org.name) if existing_org is not None else f"o_id={existing_user_org_id}"
            raise click.ClickException(
                f"User '{normalized_email}' already exists in organisation '{existing_org_name}'."
            )

        if not existing_user.active:
            existing_user.active = True
            session.commit()
        return existing_user, False

    return _create_user(session, user_email=normalized_email, password=password, org_id=org_id), True


def _ensure_admin_role(session, *, user: User) -> bool:
    user_org_id = int(user.o_id)
    admin_role = _ensure_default_roles(session, o_id=user_org_id)["admin"]
    if admin_role in user.roles:
        return False

    user.roles.append(admin_role)
    session.commit()
    return True


def _bootstrap_organisation(session, *, org_name: str) -> tuple[Organisation, bool]:
    organization, created = _get_or_create_organisation(session, org_name=org_name)
    organization_id = int(organization.o_id)
    _ensure_default_roles(session, o_id=organization_id)

    user_list_manager = PersistentUserListManager(db_session=session, o_id=organization_id)
    user_list_manager._ensure_default_lists()
    return organization, created


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


def _create_default_labels(session, *, o_id: int) -> list[str]:
    created_labels: list[str] = []
    for label_name in DEFAULT_RESET_DEV_LABELS:
        existing = session.query(Label).filter(Label.o_id == o_id, Label.label == label_name).first()
        if existing is None:
            session.add(Label(label=label_name, o_id=o_id))
            created_labels.append(label_name)
    session.commit()
    return created_labels


def _create_default_outcomes(session, *, o_id: int) -> list[str]:
    created_outcomes: list[str] = []
    for severity_rank, outcome_name in enumerate(DEFAULT_RESET_DEV_OUTCOMES, start=1):
        existing = (
            session.query(AllowedOutcome)
            .filter(AllowedOutcome.o_id == o_id, AllowedOutcome.outcome_name == outcome_name)
            .first()
        )
        if existing is not None:
            if existing.severity_rank != severity_rank:
                existing.severity_rank = severity_rank
                session.commit()
            continue

        session.add(
            AllowedOutcome(
                outcome_name=outcome_name,
                severity_rank=severity_rank,
                o_id=o_id,
            )
        )
        created_outcomes.append(outcome_name)
    session.commit()
    return created_outcomes


def _seed_reset_dev_catalogs(session, *, o_id: int) -> None:
    created_outcomes = _create_default_outcomes(session, o_id=o_id)
    created_labels = _create_default_labels(session, o_id=o_id)
    logger.info(
        "Reset-dev ensured demo catalogs. Outcomes created: %s. Labels created: %s.",
        created_outcomes or "none",
        created_labels or "none",
    )


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
@click.option("--user-email", required=True)
@click.option("--password", required=True)
@click.option(
    "--org-name",
    help="Target organisation name. If omitted and exactly one organisation exists, that organisation is used.",
)
@click.option("--admin", is_flag=True, help="Grant admin role with all permissions to the user")
def add_user(user_email, password, org_name, admin):
    db_endpoint, engine, session = _create_cli_session()

    try:
        organization = _resolve_organisation(session, org_name=org_name)
        organization_id = int(organization.o_id)
        user = _create_user(session, user_email=user_email, password=password, org_id=organization_id)
        logger.info("Added %s to organisation '%s' at %s", user.email, organization.name, db_endpoint)

        if admin:
            if _ensure_admin_role(session, user=user):
                logger.info("Assigned admin role to %s", user.email)
            else:
                logger.info("Admin role already present for %s", user.email)
    finally:
        _close_cli_session(engine, session)


@cli.command()
@click.option("--name", "org_name", required=True, help="Organisation name to create or bootstrap")
@click.option("--admin-email", required=True, help="Email for the initial admin user")
@click.option("--admin-password", required=True, help="Password for the initial admin user")
def bootstrap_org(org_name, admin_email, admin_password):
    """Create an organisation, seed defaults, and ensure an initial admin user exists."""
    db_endpoint, engine, session = _create_cli_session()

    try:
        organization, organization_created = _bootstrap_organisation(session, org_name=org_name)
        organization_id = int(organization.o_id)
        user, user_created = _get_or_create_user(
            session,
            user_email=admin_email,
            password=admin_password,
            org_id=organization_id,
        )
        admin_assigned = _ensure_admin_role(session, user=user)

        if organization_created:
            logger.info("Created organisation '%s' at %s", organization.name, db_endpoint)
        else:
            logger.info("Organisation '%s' already exists", organization.name)

        if user_created:
            logger.info("Created admin user %s", user.email)
        else:
            logger.info(
                "Admin user %s already exists in organisation '%s'; password left unchanged",
                user.email,
                organization.name,
            )

        if admin_assigned:
            logger.info("Ensured admin role for %s", user.email)
        else:
            logger.info("%s already has admin role", user.email)
    finally:
        _close_cli_session(engine, session)


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

        _, engine, session = _create_cli_session()
        try:
            logger.info("Initializing default permissions...")
            PermissionManager.db_session = session
            PermissionManager.init_default_actions()
            logger.info("Default permissions initialized")

            logger.info(f"Done initializing the DB at {db_endpoint}")
        finally:
            _close_cli_session(engine, session)

    except Exception as e:
        logger.error(f"Failed to initialize database schema: {e}")
        sys.exit(1)


@cli.command()
@click.option(
    "--org-name",
    help="Seed default roles for a specific organisation. If omitted, all existing organisations are updated.",
)
def init_permissions(org_name):
    db_endpoint, engine, session = _create_cli_session()
    logger.info("Initializing permissions at %s", db_endpoint)

    try:
        PermissionManager.db_session = session
        PermissionManager.init_default_actions()

        if org_name:
            organisations = [_resolve_organisation(session, org_name=org_name)]
        else:
            organisations = session.query(Organisation).order_by(Organisation.name).all()

        if not organisations:
            logger.info("No organisations found; initialized the global action catalogue only")
            return

        for organization in organisations:
            organization_id = int(organization.o_id)
            _ensure_default_roles(session, o_id=organization_id)
            logger.info("Default roles ready for organisation '%s'", organization.name)

        logger.info("Permissions initialized successfully")
    finally:
        _close_cli_session(engine, session)


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
@click.option(
    "--org-name",
    help="Target organisation name. If omitted and exactly one organisation exists, that organisation is used.",
)
def generate_random_data(n_rules: int, n_events: int, label_ratio: float, export_csv: str, org_name: str | None):
    if n_rules < 0 or n_events < 0:
        raise click.BadParameter("n-rules and n-events must be zero or greater")
    if not 0 <= label_ratio <= 1:
        raise click.BadParameter("label-ratio must be between 0.0 and 1.0")

    _, engine, session = _create_cli_session()

    try:
        organisation = _resolve_organisation(session, org_name=org_name)
        org_id = int(organisation.o_id)
        rng = Random()
        user_list_manager = PersistentUserListManager(db_session=session, o_id=org_id)
        set_user_list_manager(user_list_manager)
        set_organization_id(org_id)
        seed_demo_user_lists(user_list_manager)
        if label_ratio > 0 or export_csv:
            _seed_reset_dev_catalogs(session, o_id=org_id)

        fsrm: RuleManager = RuleManagerFactory.get_rule_manager("RDBRuleManager", **{"db": session, "o_id": org_id})
        rule_engine_config_producer = RDBRuleEngineConfigProducer(db=session, o_id=org_id)
        existing_rule_count = (
            session.query(RuleModel)
            .filter(
                RuleModel.o_id == org_id,
                RuleModel.rid.like("TestRule_%"),
            )
            .count()
        )
        generated_rules = build_demo_rules(n_rules=n_rules, start_index=existing_rule_count)
        for rule in generated_rules:
            session.add(RuleModel(rid=rule.rid, logic=rule.logic, description=rule.description, o_id=org_id))
        if generated_rules:
            session.commit()
            logger.info(
                "Generated %s fraud-demo rules with list-backed conditions and correlated thresholds.",
                len(generated_rules),
            )

        rule_engine_config_producer.save_config(fsrm, changed_by="cli")
        lre = LocalRuleExecutorSQL(db=session, o_id=org_id)

        existing_event_count = (
            session.query(TestingRecordLog)
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

            response = eval_and_store(lre, event, commit=False)
            record_observations(session, generated_event.event_data, org_id, commit=False)
            if index % DEMO_DATA_COMMIT_BATCH_SIZE == 0:
                session.commit()
            if index == n_events or index % 25 == 0:
                logger.info(
                    "Evaluated %s/%s demo events. Last outcome set: %s",
                    index,
                    n_events,
                    response[0]["outcome_set"],
                )
        if generated_events:
            session.commit()

        if label_ratio > 0 and generated_events:
            logger.info(f"Labeling {label_ratio * 100:.1f}% of events with realistic patterns...")

            available_labels = {label.label: label for label in session.query(Label).filter(Label.o_id == org_id).all()}
            if not available_labels:
                logger.info("No labels found in database. Skipping demo label assignment and CSV export.")

            if available_labels:
                logger.info(f"Available labels: {list(available_labels.keys())}")

                generated_event_ids = [generated_event.event_id for generated_event in generated_events]
                all_events = (
                    session.query(TestingRecordLog)
                    .filter(
                        TestingRecordLog.o_id == org_id,
                        TestingRecordLog.event_id.in_(generated_event_ids),
                    )
                    .all()
                )

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
                        event_version = get_labelable_event_version(
                            session,
                            o_id=org_id,
                            event_id=str(event_record.event_id),
                        )
                        if event_version is None:
                            continue
                        assign_event_version_label(
                            session,
                            o_id=org_id,
                            event_version=event_version,
                            label=available_labels[label_name],
                            assigned_by="cli",
                        )
                        labeled_events.append((event_record.event_id, label_name))
                        logger.info(f"Marked {event_record.event_id} as {label_name}")

                session.commit()
                logger.info(f"Successfully labeled {len(labeled_events)} events")

                if export_csv and labeled_events:
                    _export_labels_to_csv(labeled_events, export_csv)
    finally:
        _close_cli_session(engine, session)


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


def _invoke_reset_dev_generation(ctx, *, n_rules: int, n_events: int, org_name: str | None = None) -> None:
    kwargs = {
        "n_rules": n_rules,
        "n_events": n_events,
        "label_ratio": 0.3,
        "export_csv": str(DEFAULT_RESET_DEV_LABELS_CSV_PATH),
    }
    if org_name is not None:
        kwargs["org_name"] = org_name

    ctx.invoke(
        generate_random_data,
        **kwargs,
    )


@cli.command()
@click.option("--output-file", default="test_labels.csv", help="Output CSV filename")
@click.option("--n-events", default=50, help="Number of events to include in CSV")
@click.option("--unlabeled-only", is_flag=True, help="Only include events that don't have labels yet")
@click.option(
    "--org-name",
    help="Target organisation name. If omitted and exactly one organisation exists, that organisation is used.",
)
def export_test_csv(output_file: str, n_events: int, unlabeled_only: bool, org_name: str | None):
    """Export existing events to CSV for testing label uploads"""
    logger.info("Exporting events to CSV for testing...")
    _, engine, session = _create_cli_session()

    try:
        organisation = _resolve_organisation(session, org_name=org_name)
        org_id = int(organisation.o_id)

        available_labels = [label.label for label in session.query(Label).filter(Label.o_id == org_id).all()]
        if not available_labels:
            logger.warning("No labels found in database. Create labels in the UI or API before exporting a label CSV.")
            return

        query = session.query(TestingRecordLog).filter(TestingRecordLog.o_id == org_id)

        events = query.limit(n_events).all()

        if not events:
            logger.warning("No events found matching criteria.")
            return

        test_labels = []
        for event in events:
            event_version = get_labelable_event_version(session, o_id=org_id, event_id=str(event.event_id))
            if event_version is None:
                continue
            if unlabeled_only and event_version is not None:
                existing_label = (
                    session.query(EventVersionLabel)
                    .filter(EventVersionLabel.o_id == org_id, EventVersionLabel.ev_id == event_version.ev_id)
                    .first()
                )
                if existing_label is not None:
                    continue
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
    finally:
        _close_cli_session(engine, session)


@cli.command()
@click.option("--user-email", default="admin@test_org.com", help="Admin email (default: admin@test_org.com)")
@click.option("--password", default="12345678", help="Admin password (default: 12345678)")
@click.option("--org-name", default="test_org", help="Organisation name to bootstrap (default: test_org)")
@click.option("--n-rules", default=10, help="Number of rules to generate (default: 10)")
@click.option("--n-events", default=1000, help="Number of events to generate (default: 1000)")
@click.pass_context
def reset_dev(ctx, user_email, password, org_name, n_rules, n_events):
    """Reset the dev database: init-db --auto-delete + add admin user + generate fake data.

    One command to get a fresh development environment ready to use.
    """
    logger.info("=== Resetting development environment ===")

    # Step 1: init-db --auto-delete
    logger.info("Step 1/3: Initializing database...")
    ctx.invoke(init_db, auto_delete=True)

    # Step 2: bootstrap dev organisation and admin user
    logger.info("Step 2/3: Bootstrapping organisation '%s' with admin user %s...", org_name, user_email)
    ctx.invoke(bootstrap_org, org_name=org_name, admin_email=user_email, admin_password=password)

    _, engine, session = _create_cli_session()
    try:
        organisation = _resolve_organisation(session, org_name=org_name)
        org_id = int(organisation.o_id)
        _seed_reset_dev_catalogs(session, o_id=org_id)

        # Step 3: generate fake data
        logger.info(f"Step 3/3: Generating fake data ({n_rules} rules, {n_events} events)...")
        _invoke_reset_dev_generation(ctx, org_name=org_name, n_rules=n_rules, n_events=n_events)
        _ensure_default_rule_quality_pairs(
            session,
            o_id=org_id,
            created_by="cli.reset_dev",
        )
    finally:
        _close_cli_session(engine, session)

    logger.info("=== Development environment ready ===")
    logger.info("Generated label-upload CSV at: %s", DEFAULT_RESET_DEV_LABELS_CSV_PATH)
    logger.info("Organisation: %s", org_name)
    logger.info(f"Login with: {user_email} / {password}")


@cli.command()
def delete_test_data():
    _, engine, session = _create_cli_session()
    try:
        session.query(TestingRecordLog).filter(TestingRecordLog.event_id.ilike("TestEvent_%")).delete(
            synchronize_session=False
        )
        session.query(RuleModel).filter(RuleModel.rid.ilike("TestRule_%")).delete(synchronize_session=False)
        session.commit()
    finally:
        _close_cli_session(engine, session)


if __name__ == "__main__":
    cli()
