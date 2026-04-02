"""Tests for catalog seeding during CLI demo-data generation."""

from ezrules import cli as cli_module
from ezrules.models.backend_core import AllowedOutcome, Label, Organisation


def test_generate_random_data_seeds_demo_catalogs_when_labels_requested(session, monkeypatch):
    organisation = session.query(Organisation).one()

    monkeypatch.setattr(cli_module, "_create_cli_session", lambda: ("postgresql://example", object(), session))
    monkeypatch.setattr(cli_module, "_close_cli_session", lambda engine, db_session: None)

    cli_module.generate_random_data.callback(
        n_rules=0,
        n_events=0,
        label_ratio=0.3,
        export_csv="",
        org_name=str(organisation.name),
    )

    labels = {label.label for label in session.query(Label).filter(Label.o_id == int(organisation.o_id)).all()}
    outcomes = {
        outcome.outcome_name
        for outcome in session.query(AllowedOutcome).filter(AllowedOutcome.o_id == int(organisation.o_id)).all()
    }

    assert labels.issuperset(set(cli_module.DEFAULT_RESET_DEV_LABELS))
    assert outcomes.issuperset(set(cli_module.DEFAULT_RESET_DEV_OUTCOMES))
