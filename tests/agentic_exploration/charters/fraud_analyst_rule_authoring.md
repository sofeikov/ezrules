# Charter: Fraud Analyst Rule Authoring

## Persona

Fraud analyst creating production rules from observed transaction patterns.

## Mission

Explore whether a user can create, validate, promote, and understand a basic fraud rule without hidden surprises.

## Goals

- Create valid and invalid rules.
- Confirm validation messages are useful.
- Promote a rule and verify a matching live transaction receives the expected outcome.
- Verify non-matching traffic stays neutral.
- Inspect rule detail, history, and tested-event explanation.

## Hunt For

- UI says a rule is active but live evaluation disagrees.
- Rule syntax accepted in one surface but rejected elsewhere.
- Missing or misleading validation errors.
- Stale rule lists or detail pages after create/promote.
- Outcome names shown differently across editor, result, and history.

## Suggested Deterministic Follow-Up

Backend product journey or Playwright rule-authoring E2E.
