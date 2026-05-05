# Charter: Duplicate And Supersession Ledger

## Persona

Integration developer investigating transaction lifecycle behavior.

## Mission

Explore duplicate evaluation and changed-version behavior from product and API surfaces.

## Goals

- Submit the same transaction payload twice.
- Submit the same transaction ID with changed event data or effective time.
- Inspect response status, event version identifiers, and Tested Events.
- Check dashboard counts and current/latest transaction display.

## Hunt For

- Exact duplicate counted as new served traffic.
- Changed version not visible or not marked current.
- Historical versions overwritten instead of preserved.
- UI cannot explain which version produced a decision.
- API response lacks identifiers needed for reconciliation.

## Suggested Deterministic Follow-Up

Backend event-ledger contract test.
