# Charter: User List Operations

## Persona

Operations analyst maintaining trusted and risky customer lists.

## Mission

Explore list creation, entry mutation, rule usage, and downstream evaluation behavior.

## Goals

- Create a user list and add entries.
- Reference the list from a rule.
- Verify matching and non-matching evaluations.
- Remove entries and verify behavior updates.
- Inspect audit/history for list changes.

## Hunt For

- Rules using stale list values after entry changes.
- Duplicate entries or case/whitespace behavior that surprises users.
- List deletion or rename breaking rules without clear warnings.
- Audit trail missing entry-level actions.
- UI/API disagreement on list contents.

## Suggested Deterministic Follow-Up

Backend user-list mutation journey or Playwright list-management E2E.
