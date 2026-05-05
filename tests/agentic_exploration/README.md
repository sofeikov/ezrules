# Agentic Product Exploration

This folder contains browser-agent exploratory testing charters. These are not deterministic CI tests. They are prompts for agents to explore the product like real users, look for unknown breakage, and return evidence that humans can triage.

Use this layer for free testing, not release gating. When a finding is real and repeatable, convert it into a deterministic backend or Playwright test.

## How To Run A Charter

Start a private local stack first. Do not run agentic exploration against a shared database or production-like environment.

Recommended operator prompt:

```text
Use tests/agentic_exploration/RUN_CONTRACT.md and the charter at
tests/agentic_exploration/charters/<charter>.md.

Explore FRONTEND_URL=<url> and API_URL=<url>.
Login with <credentials>.
Write the final report using tests/agentic_exploration/REPORT_TEMPLATE.md.
Save any screenshots/videos under artifacts/ and reference their absolute paths.
Do not modify source code. Do not fix issues. Report findings only.
```

Run one charter per agent. If running many agents in parallel, give each agent a unique private database, user/account set, and report filename.

## What Agents Should Optimize For

- Find product behavior that feels wrong, unsafe, confusing, stale, inconsistent, or hard to recover from.
- Compare what the UI says with what actually happens after refresh, navigation, API calls, and later workflow steps.
- Stress role boundaries, lifecycle transitions, auditability, labels, analytics, and rule/evaluation explainability.
- Capture exact repro steps, data used, expected behavior, actual behavior, and evidence.
- Avoid declaring a product area correct just because one happy path worked.

## Report Outcomes

Use these verdicts:

- `PASS`: No credible issues found in the charter scope.
- `CONCERN`: Something suspicious, confusing, flaky, or under-evidenced needs human review.
- `FAIL`: A reproducible product bug, data inconsistency, permission failure, or broken journey was found.
- `BLOCKED`: The agent could not explore the charter because of setup, auth, seed data, or tool failure.

## Charter Index

- `api_key_and_evaluate_integration.md`
- `audit_trail_compliance_reviewer.md`
- `backtesting_and_async_operations.md`
- `dashboard_analytics_consistency.md`
- `duplicate_and_supersession_ledger.md`
- `event_tester_dry_run.md`
- `field_typing_and_nested_payloads.md`
- `fraud_analyst_rule_authoring.md`
- `labels_and_rule_quality.md`
- `navigation_and_session_resilience.md`
- `negative_inputs_and_validation.md`
- `notifications_and_alerts.md`
- `outcome_configuration.md`
- `permissions_role_boundary.md`
- `rule_edit_lifecycle.md`
- `rule_ordering_first_match.md`
- `settings_runtime_modes.md`
- `shadow_and_rollout.md`
- `tested_events_explainability.md`
- `user_list_operations.md`
