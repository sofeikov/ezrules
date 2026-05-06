# Charter: Settings And Runtime Modes

## Persona

Operations admin changing organization-wide runtime behavior.

## Mission

Explore settings that affect evaluation behavior and whether changes are clear, reversible, and audited.

## Goals

- Change main-rule execution mode if available.
- Change rule-quality or analytics settings if available.
- Toggle AI or strict/runtime settings if available.
- Verify downstream behavior changes after settings updates.
- Inspect audit/history for setting changes.

## Hunt For

- Setting appears saved but runtime behavior does not change.
- Dangerous setting changes without confirmation.
- Unsaved changes lost silently.
- Audit trail missing settings changes.
- Settings page shows stale values after refresh.

## Suggested Deterministic Follow-Up

Backend runtime settings test or Playwright settings E2E.
