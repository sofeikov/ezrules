# Charter: Outcome Configuration

## Persona

Operations admin configuring business outcomes.

## Mission

Explore configured outcomes and how they affect rule authoring, validation, severity, and result display.

## Goals

- Inspect configured outcomes.
- Create rules using valid and invalid outcomes.
- Change severity/rank if supported.
- Evaluate events returning multiple outcomes.
- Confirm UI displays configured outcomes consistently.

## Hunt For

- Unknown outcomes accepted.
- Valid outcomes rejected because of case or formatting confusion.
- Severity ordering inconsistent between response, dashboard, and UI.
- Outcome changes not reflected in editor autocomplete or validation.
- Old outcomes remain usable unexpectedly.

## Suggested Deterministic Follow-Up

Backend outcome validation/resolution test.
