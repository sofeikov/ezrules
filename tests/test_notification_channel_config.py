import datetime

import pytest

from ezrules.backend.notifications.dispatcher import CHANNEL_ADAPTERS, NotificationMessage, dispatch_notification
from ezrules.core.notification_channel_config import REDACTED_VALUE
from ezrules.models.backend_core import (
    AlertIncident,
    AlertRule,
    NotificationAttempt,
    NotificationChannel,
    NotificationPolicy,
    Organisation,
)


def test_notification_channel_config_is_encrypted_and_redacted():
    config = {
        "url": "https://hooks.example.com/secret-token",
        "headers": {"Authorization": "Bearer api-token", "X-Trace": "visible"},
        "signing_secret": "shared-secret",
        "timeout_seconds": 10,
    }

    channel = NotificationChannel(
        o_id=1,
        name="Risk webhook",
        channel_type="webhook",
        enabled=True,
        config=config,
    )

    assert channel.config == config
    assert "secret-token" not in channel.config_encrypted
    assert "api-token" not in channel.config_encrypted
    assert "shared-secret" not in channel.config_encrypted
    assert channel.redacted_config == {
        "url": REDACTED_VALUE,
        "headers": {"Authorization": REDACTED_VALUE, "X-Trace": "visible"},
        "signing_secret": REDACTED_VALUE,
        "timeout_seconds": 10,
    }


def test_notification_channel_config_rejects_unknown_and_missing_fields():
    with pytest.raises(ValueError, match="Missing required config field"):
        NotificationChannel(o_id=1, name="Slack", channel_type="slack", config={})

    with pytest.raises(ValueError, match="Unsupported config field"):
        NotificationChannel(
            o_id=1,
            name="Webhook",
            channel_type="webhook",
            config={"url": "https://hooks.example.com/a", "plaintext_token": "nope"},
        )


def test_dispatch_failure_persists_redacted_error(session, monkeypatch):
    org = session.query(Organisation).filter(Organisation.o_id == 1).one()
    rule = AlertRule(
        o_id=int(org.o_id),
        name="Cancel spike",
        outcome="CANCEL",
        threshold=1,
        window_seconds=3600,
        cooldown_seconds=1800,
        enabled=True,
    )
    channel = NotificationChannel(
        o_id=int(org.o_id),
        name="Escalation webhook",
        channel_type="webhook",
        enabled=True,
        config={
            "url": "https://hooks.example.com/hidden-token",
            "headers": {"Authorization": "Bearer hidden-auth"},
            "signing_secret": "hidden-signing-secret",
        },
    )
    session.add_all([rule, channel])
    session.flush()
    incident = AlertIncident(
        o_id=int(org.o_id),
        alert_rule_id=int(rule.ar_id),
        outcome="CANCEL",
        observed_count=2,
        threshold=1,
        window_start=datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=1),
        window_end=datetime.datetime.now(datetime.UTC),
        dedupe_key="redaction-test",
    )
    session.add(incident)
    session.flush()
    session.add(
        NotificationPolicy(
            o_id=int(org.o_id),
            alert_rule_id=int(rule.ar_id),
            notification_channel_id=int(channel.nc_id),
            enabled=True,
        )
    )

    class FailingWebhookAdapter:
        channel_type = "webhook"

        def send(self, db, channel, message):
            raise RuntimeError(
                "failed "
                f"{channel.config['url']} "
                f"{channel.config['headers']['Authorization']} "
                f"{channel.config['signing_secret']}"
            )

    monkeypatch.setitem(CHANNEL_ADAPTERS, "webhook", FailingWebhookAdapter())

    dispatch_notification(
        session,
        o_id=int(org.o_id),
        alert_rule_id=int(rule.ar_id),
        incident_id=int(incident.ai_id),
        message=NotificationMessage(
            title="CANCEL spike detected",
            body="2 CANCEL decisions in the last 60 minutes.",
            severity="critical",
            source_type="alert_incident",
            source_id=int(incident.ai_id),
        ),
    )

    attempt = session.query(NotificationAttempt).one()
    assert attempt.status == "failure"
    assert "hidden-token" not in str(attempt.error)
    assert "hidden-auth" not in str(attempt.error)
    assert "hidden-signing-secret" not in str(attempt.error)
    assert str(attempt.error).count(REDACTED_VALUE) == 3
