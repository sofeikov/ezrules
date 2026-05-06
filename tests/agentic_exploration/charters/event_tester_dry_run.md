# Charter: Event Tester Dry Run

## Persona

Analyst testing a proposed event before sending real traffic.

## Mission

Explore whether Event Tester behaves like evaluation without persistence side effects.

## Goals

- Run dry-run events that match and miss rules.
- Compare dry-run result with live evaluation for equivalent payloads.
- Verify dry runs do not appear as served Tested Events unless explicitly expected.
- Try malformed JSON and missing fields.
- Try rollout/allowlist interactions if available.

## Hunt For

- Dry run creating persistent served events.
- Dry-run result disagreeing with live evaluation for same active config.
- Error state that loses user input.
- Invalid payload accepted silently.
- Missing explanation of why no rule matched.

## Suggested Deterministic Follow-Up

Backend event-test isolation journey or Playwright Event Tester E2E.
