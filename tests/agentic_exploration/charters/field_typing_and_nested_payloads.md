# Charter: Field Typing And Nested Payloads

## Persona

Integration developer sending realistic nested transaction payloads.

## Mission

Explore nested field references, type coercion, missing fields, and payload display.

## Goals

- Create rules using nested fields such as `$customer.profile.age` or `$device.trust_score`.
- Submit numeric strings, missing fields, nulls, and nested objects.
- Inspect validation, evaluation, Tested Events, and referenced-field display.
- Try payloads with unexpected extra fields.

## Hunt For

- Nested rule compiles but fails at runtime.
- Type coercion differs between dry run, live evaluation, and backtesting.
- Missing fields produce unclear errors or wrong outcomes.
- Referenced-field highlighting breaks nested paths.
- Payload viewer corrupts nested data.

## Suggested Deterministic Follow-Up

Backend nested-field evaluator test or Playwright payload explainability E2E.
