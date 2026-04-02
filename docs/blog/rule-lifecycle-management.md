# Rule Lifecycle Management in ezrules: Draft, Promote, Roll Back, Archive with Audit Trail

Rule engines usually fail at one of two extremes:

- Every edit is live immediately, which is fast but risky.
- Every edit requires an external process, which is safe but slow.

ezrules now supports an explicit lifecycle so teams can move fast without losing control: `draft` -> `active` -> `archived`, with promotion approvals captured in the audit trail and rollback available when a historical revision needs to be restored as a new draft.

## Why lifecycle controls matter

If a rule change can go live directly from an edit, then you can accidentally ship unreviewed logic. If a rule change requires manual coordination outside the system, then iteration slows down and people work around process.

The useful middle ground is to separate:

- rule authoring (`draft`)
- rule deployment (`active`)
- retirement (`archived`)

This gives you cleaner change control and a clear operational state for every rule.

## What is now stored per rule

Each rule now includes lifecycle metadata:

- `status`: `draft`, `active`, or `archived`
- `effective_from`: when the active version became effective
- `approved_by`: user id who approved promotion
- `approved_at`: when promotion was approved

The same metadata is snapshotted into `rules_history`, so lifecycle transitions and approver chain context are preserved in historical revisions.

## API behavior by lifecycle

The lifecycle is enforced by API behavior:

- `POST /api/v2/rules` creates a `draft` rule
- `PUT /api/v2/rules/{id}` saves edits as `draft` and clears previous approval metadata by default
- `POST /api/v2/rules/{id}/rollback` restores a historical revision's logic and description into a brand new `draft`
- `POST /api/v2/rules/{id}/promote` moves `draft` to `active` and records approver + approval timestamp
- `POST /api/v2/rules/{id}/archive` moves a rule to `archived`
- `DELETE /api/v2/rules/{id}` deletes the rule (requires `DELETE_RULE`)

Production evaluation config now includes only `active` rules.

An org can opt into `auto_promote_active_rule_updates` through the runtime settings API or **Settings → General**. When that setting is enabled, editing an already active rule keeps it active and rewrites the production config immediately, but the caller still needs `PROMOTE_RULES` in addition to `MODIFY_RULE`.

```mermaid
flowchart LR
    A[Create rule] --> B[draft]
    B --> C[Edit rule]
    C --> B
    B --> D[Promote]
    D --> E[active]
    E --> F[Edit or detect issue]
    F --> G[Rollback to prior revision]
    G --> B
    E --> H[Archive]
    H --> I[archived]
```

## Promotion is a first-class approval step

Promotion is no longer an implicit side effect of editing. It is an explicit operation that records:

- who approved
- when it was approved
- when it became effective

That gives you a defensible trail for internal governance and external audits, while keeping authoring fast for rule editors.

## Archive is not delete

Archiving is useful when you need to retire a rule but keep full context.

- `archived` rules are no longer active in production config
- historical versions and metadata remain available
- teams can distinguish "no longer used" from "removed forever"

Use delete when you intentionally want permanent removal. Use archive when you want operational retirement with history intact.

## Rollback is not history deletion

Rollback does not rewind the database in place and it does not remove newer revisions.

- the selected historical revision remains in history
- the current revision remains in history
- rollback creates a new `draft` version using the older logic and description
- the rollback action itself is recorded in audit history

This is the safer operational model: you recover known-good logic quickly without destroying evidence of what changed.

## Example: promote and archive

```bash
# Roll back rule 42 to revision 3 (creates a new draft)
curl -X POST http://localhost:8888/api/v2/rules/42/rollback \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{"revision_number": 3}'

# Promote draft rule 42
curl -X POST http://localhost:8888/api/v2/rules/42/promote \
  -H "Authorization: Bearer <access_token>"

# Archive rule 42
curl -X POST http://localhost:8888/api/v2/rules/42/archive \
  -H "Authorization: Bearer <access_token>"
```

## How this fits with shadow deployment

Lifecycle and shadow solve different concerns:

- Lifecycle controls whether a rule is draft, active, or archived in production management flow.
- Shadow deployment validates candidate behavior on live traffic before promotion.

A practical sequence is:

1. Edit rule in draft
2. (Optional) deploy to shadow for live validation
3. Roll back to a known-good revision if a newer draft or active version proves wrong
4. Promote when approved
5. Archive when rule is retired

## Net effect

You get a cleaner rule lifecycle without adding operational friction:

- safer releases through explicit promotion
- faster recovery through auditable rollback
- auditable approval chain
- clear operational state in UI and API
- predictable retirement path through archive

---

Related docs:

- [Manager API](../api-reference/manager-api.md)
- [Creating Rules](../user-guide/creating-rules.md)
- [Shadow Deployment guide](../user-guide/shadow-deployment.md)
