# Charter: Backtesting And Async Operations

## Persona

Analyst validating a rule against historical traffic.

## Mission

Explore backtesting and async job behavior, including progress, completion, errors, and result interpretation.

## Goals

- Start a backtest for a rule or draft if available.
- Observe progress/polling and final results.
- Compare result counts with known seeded/evaluated traffic.
- Try navigation away and back during an active job.
- Trigger a known invalid backtest if possible.

## Hunt For

- Job appears stuck while backend completed or failed.
- Result counts disagree with visible data.
- Errors hidden behind generic failure text.
- Duplicate jobs created by repeated clicks.
- Results attached to the wrong rule or draft.

## Suggested Deterministic Follow-Up

Backend task/state test or Playwright async polling E2E.
