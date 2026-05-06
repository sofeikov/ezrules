# Charter: Notifications And Alerts

## Persona

Risk operations lead monitoring spikes and incidents.

## Mission

Explore alert creation, trigger behavior, in-app notifications, and read/unread state.

## Goals

- Configure or inspect alert rules if available.
- Generate traffic that should and should not trigger alerts.
- Check notification bell/list behavior.
- Mark notifications read/unread if supported.
- Inspect whether incidents link to relevant traffic or outcomes.

## Hunt For

- Alerts not firing for obvious threshold breaches.
- Duplicate alerts for the same incident.
- Notification unread state stale after refresh.
- Alerts based on duplicate or dry-run traffic.
- Missing context to investigate the incident.

## Suggested Deterministic Follow-Up

Backend alert detection test or Playwright notification E2E.
