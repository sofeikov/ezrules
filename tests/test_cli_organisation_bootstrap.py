"""Tests for CLI organisation bootstrap and org resolution helpers."""

import click
import pytest
from click.testing import CliRunner

from ezrules import cli as cli_module
from ezrules.models.backend_core import Organisation, Role


def test_resolve_organisation_returns_only_existing_org(session):
    organisation = cli_module._resolve_organisation(session)

    assert organisation.name == "test_org"


def test_resolve_organisation_requires_name_when_multiple_orgs_exist(session):
    session.add(Organisation(name="other_org"))
    session.commit()

    with pytest.raises(click.ClickException, match="Multiple organisations exist"):
        cli_module._resolve_organisation(session)


def test_bootstrap_organisation_creates_roles_and_is_idempotent(session):
    organisation, created = cli_module._bootstrap_organisation(session, org_name="acme")

    assert created is True
    assert organisation.name == "acme"
    assert {role.name for role in session.query(Role).filter(Role.o_id == int(organisation.o_id)).all()} == {
        "admin",
        "readonly",
        "rule_editor",
    }

    same_organisation, created_again = cli_module._bootstrap_organisation(session, org_name="acme")

    assert created_again is False
    assert int(same_organisation.o_id) == int(organisation.o_id)
    assert session.query(Role).filter(Role.o_id == int(organisation.o_id)).count() == 3


def test_bootstrap_org_command_wires_helpers(monkeypatch):
    runner = CliRunner()
    calls: list[tuple[str, object]] = []
    fake_engine = object()
    fake_session = object()

    class FakeOrganisation:
        name = "acme"
        o_id = 7

    class FakeUser:
        email = "admin@example.com"

    monkeypatch.setattr(cli_module, "_create_cli_session", lambda: ("postgresql://example", fake_engine, fake_session))
    monkeypatch.setattr(
        cli_module,
        "_close_cli_session",
        lambda engine, session: calls.append(("close", (engine, session))),
    )
    monkeypatch.setattr(
        cli_module,
        "_bootstrap_organisation",
        lambda session, *, org_name: calls.append(("bootstrap", org_name)) or (FakeOrganisation(), True),
    )
    monkeypatch.setattr(
        cli_module,
        "_get_or_create_user",
        lambda session, *, user_email, password, org_id: calls.append(("user", (user_email, password, org_id)))
        or (FakeUser(), True),
    )
    monkeypatch.setattr(
        cli_module,
        "_ensure_admin_role",
        lambda session, *, user: calls.append(("admin", user.email)) or True,
    )

    result = runner.invoke(
        cli_module.cli,
        [
            "bootstrap-org",
            "--name",
            "acme",
            "--admin-email",
            "admin@example.com",
            "--admin-password",
            "super-secret",
        ],
    )

    assert result.exit_code == 0
    assert calls == [
        ("bootstrap", "acme"),
        ("user", ("admin@example.com", "super-secret", 7)),
        ("admin", "admin@example.com"),
        ("close", (fake_engine, fake_session)),
    ]


def test_invoke_reset_dev_generation_passes_org_name():
    invocations: list[tuple[object, dict]] = []

    class DummyContext:
        def invoke(self, command, **kwargs):
            invocations.append((command, kwargs))

    cli_module._invoke_reset_dev_generation(DummyContext(), org_name="dev_org", n_rules=7, n_events=15)

    assert invocations == [
        (
            cli_module.generate_random_data,
            {
                "n_rules": 7,
                "n_events": 15,
                "label_ratio": 0.3,
                "export_csv": str(cli_module.DEFAULT_RESET_DEV_LABELS_CSV_PATH),
                "org_name": "dev_org",
            },
        )
    ]
