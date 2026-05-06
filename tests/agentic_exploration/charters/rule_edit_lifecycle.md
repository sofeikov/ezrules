# Charter: Rule Edit Lifecycle

## Persona

Senior analyst maintaining active rules.

## Mission

Explore edit, draft, promote, pause, resume, and archive behavior around an existing active rule.

## Goals

- Edit an active rule and determine whether new logic serves immediately or waits for promotion.
- Pause and resume a rule, then verify live traffic behavior after each state change.
- Refresh and revisit detail/list pages after each transition.
- Inspect history entries and status labels.

## Hunt For

- Active and draft states that contradict served behavior.
- Old logic still serving after promotion.
- New logic serving before expected.
- Missing actor/timestamp/status transitions in history.
- Buttons enabled in invalid lifecycle states.

## Suggested Deterministic Follow-Up

Backend lifecycle journey plus Playwright state-transition E2E.
