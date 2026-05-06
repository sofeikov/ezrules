# Charter: API Key And Evaluate Integration

## Persona

Integration developer wiring transaction evaluation into another system.

## Mission

Explore API key lifecycle and `/api/v2/evaluate` behavior from a client perspective.

## Goals

- Create or locate an API key.
- Submit valid, invalid, duplicate, and changed-version evaluation requests.
- Inspect response fields and error messages.
- Revoke or rotate the key if supported, then retry.
- Compare API responses with Tested Events or dashboard visibility.

## Hunt For

- Invalid keys producing side effects.
- Duplicate requests creating duplicate events.
- Response fields missing identifiers needed for tracing.
- Revoked keys still working.
- API docs, UI, and runtime behavior disagreeing.

## Suggested Deterministic Follow-Up

Backend evaluator contract test or API-key lifecycle test.
