# Charter: Shadow And Rollout

## Persona

Risk lead trialing a candidate rule change before full promotion.

## Mission

Explore shadow and rollout behavior, especially whether users can understand which logic served the customer-facing outcome.

## Goals

- Start a shadow comparison or rollout candidate if available.
- Send events that make control and candidate differ.
- Inspect rollout/shadow result surfaces.
- Confirm traffic percent behavior is understandable.
- Stop or change the deployment and verify behavior.

## Hunt For

- Candidate result returned when control should serve, or vice versa.
- Provenance missing from result/history.
- Rollout percent saved but not applied.
- UI reports no data while logs exist.
- Stopping rollout leaves stale candidate behavior.

## Suggested Deterministic Follow-Up

Backend rollout provenance journey or Playwright rollout management E2E.
