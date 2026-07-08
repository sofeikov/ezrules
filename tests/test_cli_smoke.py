"""End-to-end smoke coverage for core database-backed CLI flows."""

import csv
import os
import subprocess
import sys
import uuid
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _private_cli_db_url() -> str:
    base_url = make_url(os.environ.get("EZRULES_DB_ENDPOINT", "postgresql://postgres:root@localhost:5432/tests"))
    database_name = base_url.database or "tests"
    return base_url.set(database=f"{database_name}_cli_{uuid.uuid4().hex[:8]}").render_as_string(hide_password=False)


def _drop_database(db_url: str) -> None:
    parsed_url = make_url(db_url)
    database_name = parsed_url.database
    if database_name is None:
        return

    admin_engine = create_engine(parsed_url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        quoted_database_name = admin_engine.dialect.identifier_preparer.quote(database_name)
        with admin_engine.connect() as connection:
            connection.execute(
                text(
                    """
                    SELECT pg_terminate_backend(pid)
                    FROM pg_stat_activity
                    WHERE datname = :database_name AND pid <> pg_backend_pid()
                    """
                ),
                {"database_name": database_name},
            )
            connection.execute(text(f"DROP DATABASE IF EXISTS {quoted_database_name}"))
    finally:
        admin_engine.dispose()


def _run_cli(db_url: str, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update(
        {
            "EZRULES_APP_SECRET": "test-secret",
            "EZRULES_DB_ENDPOINT": db_url,
            "EZRULES_ORG_ID": "1",
            "EZRULES_TESTING": "true",
        }
    )
    result = subprocess.run(
        [sys.executable, "-m", "ezrules.cli", *args],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if check:
        assert result.returncode == 0, result.stderr or result.stdout
    return result


def _scalar(engine, query: str, params: dict | None = None):
    with engine.connect() as connection:
        return connection.execute(text(query), params or {}).scalar_one()


def test_core_cli_flows_round_trip_against_private_database(tmp_path):
    db_url = _private_cli_db_url()
    _drop_database(db_url)

    engine = None
    try:
        _run_cli(db_url, "init-db", "--auto-delete")
        engine = create_engine(db_url)

        assert (
            _scalar(
                engine,
                """
                SELECT COUNT(*)
                FROM information_schema.tables
                WHERE table_schema = 'public'
                AND table_name IN ('user', 'role', 'organisation')
                """,
            )
            == 3
        )

        org_name = "cli_test_org"
        admin_email = "test@example.com"
        _run_cli(
            db_url,
            "bootstrap-org",
            "--name",
            org_name,
            "--admin-email",
            admin_email,
            "--admin-password",
            "testpass123",
        )

        assert (
            _scalar(engine, "SELECT name FROM organisation WHERE name = :org_name", {"org_name": org_name}) == org_name
        )
        assert _scalar(engine, 'SELECT email FROM "user" WHERE email = :email', {"email": admin_email}) == admin_email
        assert _scalar(engine, 'SELECT password FROM "user" WHERE email = :email', {"email": admin_email}).startswith(
            "$2b$"
        )
        assert _scalar(engine, 'SELECT active FROM "user" WHERE email = :email', {"email": admin_email}) is True
        assert (
            _scalar(
                engine,
                """
                SELECT COUNT(*)
                FROM "role" role
                JOIN roles_users roles_users ON roles_users.role_id = role.id
                JOIN "user" app_user ON app_user.id = roles_users.user_id
                WHERE app_user.email = :email AND role.name = 'admin'
                """,
                {"email": admin_email},
            )
            == 1
        )

        _run_cli(db_url, "init-permissions", "--org-name", org_name)
        assert (
            _scalar(
                engine,
                """
                SELECT COUNT(*)
                FROM "role"
                WHERE o_id = (SELECT o_id FROM organisation WHERE name = :org_name)
                AND name IN ('admin', 'readonly', 'rule_editor')
                """,
                {"org_name": org_name},
            )
            == 3
        )
        assert _scalar(engine, "SELECT COUNT(*) FROM actions WHERE name IS NOT NULL") > 0

        member_email = "member@example.com"
        _run_cli(
            db_url,
            "add-user",
            "--org-name",
            org_name,
            "--user-email",
            member_email,
            "--password",
            "memberpass123",
        )
        assert _scalar(engine, 'SELECT email FROM "user" WHERE email = :email', {"email": member_email}) == member_email

        duplicate_result = _run_cli(
            db_url,
            "add-user",
            "--org-name",
            org_name,
            "--user-email",
            member_email,
            "--password",
            "newpass",
            check=False,
        )
        assert duplicate_result.returncode != 0
        assert _scalar(engine, 'SELECT COUNT(*) FROM "user" WHERE email = :email', {"email": member_email}) == 1

        initial_rules = _scalar(engine, "SELECT COUNT(*) FROM rules")
        initial_events = _scalar(engine, "SELECT COUNT(*) FROM event_versions")
        _run_cli(
            db_url,
            "generate-random-data",
            "--org-name",
            org_name,
            "--n-rules",
            "5",
            "--n-events",
            "10",
            "--label-ratio",
            "1.0",
        )

        assert _scalar(engine, "SELECT COUNT(*) FROM rules") > initial_rules
        assert _scalar(engine, "SELECT COUNT(*) FROM event_versions") > initial_events
        assert _scalar(engine, "SELECT COUNT(*) FROM event_version_labels") > 0

        csv_path = tmp_path / "test_export.csv"
        _run_cli(
            db_url,
            "export-test-csv",
            "--org-name",
            org_name,
            "--output-file",
            str(csv_path),
            "--n-events",
            "5",
        )

        with csv_path.open(newline="") as handle:
            rows = list(csv.reader(handle))

        assert rows
        assert all(len(row) == 2 for row in rows)

        _run_cli(db_url, "delete-test-data")

        assert _scalar(engine, "SELECT COUNT(*) FROM event_versions WHERE transaction_id LIKE 'TestEvent_%'") == 0
        assert _scalar(engine, "SELECT COUNT(*) FROM rules WHERE rid LIKE 'TestRule_%'") == 0
    finally:
        if engine is not None:
            engine.dispose()
        _drop_database(db_url)
