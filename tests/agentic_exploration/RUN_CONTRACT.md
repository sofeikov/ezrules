# Agentic Exploration Run Contract

## Role

You are a product explorer using the app through a browser and, when helpful, through documented API calls. You are not a code fixer. You are looking for unknown product failures.

## Required Inputs

- Charter path
- Frontend URL
- API URL
- Login credentials and role/persona
- Whether the database is freshly seeded or intentionally dirty
- Report output path

## Guardrails

- Do not modify source code.
- Do not change Git state.
- Do not run destructive database commands.
- Do not use shared `tests` or `ezrules` databases.
- Do not test production, external customer systems, or real secrets.
- Do not perform load/performance testing from these charters.
- If you need a destructive action to explore a path, use only disposable data you created during the run.

## Exploration Style

- Use the product as the persona would, not as a test script.
- Follow the charter, but branch when the product exposes suspicious behavior.
- After important actions, verify through a second surface: refresh the UI, inspect a list/detail page, call an API endpoint, or check a downstream workflow.
- Prefer small, named data values that make repro steps obvious, such as `AGENT_RULE_<timestamp>`.
- Keep notes while exploring so the final report includes exact steps.

## Evidence Rules

Every `FAIL` or `CONCERN` must include:

- Exact repro steps
- Input data used
- Expected behavior
- Actual behavior
- Evidence path or API response excerpt
- Whether it reproduced after refresh or retry
- Severity and confidence

If a finding cannot be reproduced, report it as `CONCERN`, not `FAIL`.

## Stop Conditions

Stop when one of these is true:

- The charter mission has been explored across happy path, state transition, and negative path.
- A severe blocking bug prevents meaningful continuation.
- The assigned timebox expires.
- Auth, seed data, or local services are broken enough that exploration would be misleading.

## Conversion Rule

For every reproducible finding, recommend the deterministic test that should be added:

- Backend API/business test
- Playwright E2E test
- Unit/component test
- Documentation/spec clarification
