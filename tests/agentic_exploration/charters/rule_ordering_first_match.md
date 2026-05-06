# Charter: Rule Ordering And First Match

## Persona

Risk operations lead configuring rule priority.

## Mission

Explore ordered main-rule execution and whether first-match behavior is understandable and correct.

## Goals

- Create overlapping rules with different outcomes.
- Enable first-match mode if available.
- Reorder rules and evaluate the same transaction after each order change.
- Confirm rule list order, served outcome, and tested-event explanation agree.

## Hunt For

- Reordering appears successful but evaluation still uses old order.
- UI hides ordering while first-match mode is enabled.
- Multiple matches persist when first-match should stop.
- Audit/history does not record order changes.
- Confusing behavior when rules have equal or missing order.

## Suggested Deterministic Follow-Up

Backend ordered-execution universe scenario or Playwright ordering E2E.
