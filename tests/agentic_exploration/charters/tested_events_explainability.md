# Charter: Tested Events Explainability

## Persona

Fraud analyst investigating why a transaction received a decision.

## Mission

Explore whether Tested Events explains served decisions clearly and accurately.

## Goals

- Generate events that hit one rule, multiple rules, allowlist rules, and no rules.
- Open Tested Events and inspect detail/explanation views.
- Confirm referenced fields and triggered rules match rule logic.
- Label or filter events if supported.
- Revisit after rule edits to see whether historical explanation remains understandable.

## Hunt For

- Missing triggered rules.
- Referenced fields absent or wrong.
- Historical events appearing to use current rule logic incorrectly.
- Filtering/search hiding events unexpectedly.
- Event payload display losing nested fields or data types.

## Suggested Deterministic Follow-Up

Backend Tested Events API test or Playwright investigation flow.
