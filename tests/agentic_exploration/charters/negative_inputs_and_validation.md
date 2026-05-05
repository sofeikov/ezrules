# Charter: Negative Inputs And Validation

## Persona

Adversarial product explorer trying odd but realistic user input.

## Mission

Explore validation, error recovery, and side-effect safety for malformed input.

## Goals

- Try invalid rule syntax, unknown outcomes, duplicate names, empty fields, huge values, nulls, and odd whitespace.
- Try invalid API payloads.
- Verify failed operations do not create partial data.
- Refresh after failures and inspect lists/history.

## Hunt For

- Error response with persisted side effects.
- UI shows success despite backend failure.
- Duplicate objects created after retries.
- Validation message does not identify the field or problem.
- User input lost unnecessarily after correctable errors.

## Suggested Deterministic Follow-Up

Backend negative-path business test or Playwright validation E2E.
