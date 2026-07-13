# Evaluator API

The evaluator endpoint is part of the unified FastAPI service.
It executes the active rule set against one event payload and stores results.

## Base URL

`http://localhost:8888`

## Run Locally

--8<-- "snippets/start-api.md"

## Authentication

`/api/v2/evaluate` requires credentials on every request.
Two methods are accepted for live evaluation:

### API Key (recommended for service-to-service)

Pass the raw key in the `X-API-Key` header:

```bash
curl -X POST http://localhost:8888/api/v2/evaluate \
  -H "X-API-Key: ezrk_<your-key>" \
  -H "Content-Type: application/json" \
  -d '{"transaction_id": "txn_1", "effective_at": "2026-04-23T12:00:00Z", "event_data": {}}'
```

API keys are created via `POST /api/v2/api-keys` (requires `MANAGE_API_KEYS` permission).
The raw key is shown **once** at creation time and is never retrievable again.

### Bearer token (for existing user sessions)

Pass a valid JWT access token obtained from `POST /api/v2/auth/login`:

```bash
curl -X POST http://localhost:8888/api/v2/evaluate \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{"transaction_id": "txn_1", "effective_at": "2026-04-23T12:00:00Z", "event_data": {}}'
```

`/api/v2/event-tests` accepts bearer-token user sessions only and requires the `submit_test_events` permission.

## Endpoint

### Evaluate Event

`POST /api/v2/evaluate`

Evaluates a transaction version against the current rule configuration, resolves any conflicting outcomes using the configured outcome hierarchy, and stores evaluation results in the canonical evaluation ledger.

Each successful non-duplicate request appends an event version for the supplied `transaction_id` and writes an immutable served-decision record linked to that exact version. Re-submitting the same `transaction_id`, `effective_at`, payload hash, and terminal flag returns the existing evaluation with `evaluation_status=duplicate`. Re-submitting the transaction with new facts creates a later event version; if it becomes current, the prior current decision is marked superseded.

#### Allowlist Short-Circuiting

If one or more active allowlist rules match an event:

- the allowlist result is returned immediately
- the main rule set is skipped for the returned result
- `rule_results` contains the matching allowlist rules only

Allowlist rules must return the configured neutral outcome using `!OUTCOME` syntax. The current runtime setting is `neutral_outcome`, which defaults to `RELEASE`, so the canonical allowlist return is `!RELEASE` unless your organisation changes that value.

#### Request Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `transaction_id` | `string` | Yes | Stable real-world transaction identifier |
| `effective_at` | `datetime` | Yes | When this version became true in the source system |
| `observed_at` | `datetime` | No | When this version was observed; defaults to evaluator ingest time |
| `terminal_state` | `boolean` | No | Whether this version closes the transaction lifecycle |
| `event_data` | `object` | Yes | Event payload used by rules (fields accessed via `$field`) |

#### Example Request

```bash
curl -X POST http://localhost:8888/api/v2/evaluate \
  -H "X-API-Key: ezrk_<your-key>" \
  -H "Content-Type: application/json" \
  -d '{
    "transaction_id": "txn_123456",
    "effective_at": "2026-04-23T12:00:00Z",
    "observed_at": "2026-04-23T12:00:03Z",
    "event_data": {
      "amount": 15000,
      "user_id": "user_42",
      "country": "US"
    }
  }'
```

#### Example Response

```json
{
  "transaction_id": "txn_123456",
  "outcome_counters": {
    "HOLD": 1
  },
  "outcome_set": [
    "HOLD"
  ],
  "resolved_outcome": "HOLD",
  "rule_results": {
    "7": "HOLD"
  },
  "event_version": 1,
  "event_version_id": 81,
  "evaluation_id": 42,
  "evaluation_status": "new",
  "is_current": true,
  "superseded_evaluation_id": null
}
```

`resolved_outcome` is the highest-severity outcome after applying the ordering configured under **Settings → Outcome Resolution**.

`event_version` is the append-only version number for the supplied `transaction_id` within the caller's organisation. `event_version_id` identifies the immutable payload version; `evaluation_id` identifies the immutable served-decision record used by Tested Events, rollout/shadow provenance, replay, and downstream analysis. `evaluation_status` is `new`, `duplicate`, or `superseding`.

When allowlist rules match, `resolved_outcome` is derived from the allowlist result and the main rules do not contribute to the returned evaluation.

#### Field Normalization

Before rules are executed, ezrules validates configured required fields and then casts present non-null values to their configured types (see [Field Type Management](../user-guide/field-types.md)). Both casting and strict lookups understand canonical dotted nested paths such as `customer.profile.age`. Unconfigured fields pass through unchanged.

If a field is configured with `required=true`, the event is rejected when that field is missing or explicitly `null`:

```json
{
  "detail": "Required field 'amount' is missing or null"
}
```

If a value cannot be cast to the configured type, the request is rejected with `400`:

```json
{
  "detail": "Cannot cast field 'amount' value 'not-a-number' to integer"
}
```

If rule logic references a field that is absent from `event_data`, the request is also rejected with `400` and no event is stored:

```json
{
  "detail": "Rule 'RULE_123' lookup failed: field 'country' is missing from the event"
}
```

Nested lookups return the full dotted path in the same format:

```json
{
  "detail": "Rule 'RULE_123' lookup failed: field 'customer.profile.age' is missing from the event"
}
```

Rules can also reference active computed features with `stat[entity.feature_name]`. These include aggregate history features and bounded graph features over configured transaction entity fields. Feature resolution uses the transaction version that is current as of the request's `effective_at` timestamp, so corrected transaction versions do not double-count aggregates or graph relationships and future-effective versions do not leak into historical results. Aggregate windows are start-inclusive and end-exclusive, with type-sensitive entity/filter matching and trace warnings for excluded invalid numeric inputs. Successful live evaluations persist feature snapshot metadata linked to the served decision; dry-run event tests do not. If a referenced stat is missing, inactive, or exceeds feature guardrails, evaluation returns `400` and does not store the event.

Field observations are also recorded on each successful call, contributing to the **Observed Fields** data visible in the UI. Observations include canonical dotted nested paths as well as parent objects. Live evaluation now buffers those observation writes through Redis and a periodic Celery drain, so observation listings are eventually consistent rather than immediate.

### Test Event

`POST /api/v2/event-tests`

Dry-runs an event against the current rule configuration without writing event versions, served-decision records, Tested Events rows, rollout/shadow logs, or field observations.

This endpoint uses the same request fields as `POST /api/v2/evaluate`, applies the same field normalization rules, honors allowlist short-circuiting, uses the configured main-rule execution mode, applies active rollout selection, and resolves the final outcome with the configured outcome hierarchy.

#### Required Permission

`submit_test_events`

#### Example Request

```bash
curl -X POST http://localhost:8888/api/v2/event-tests \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "transaction_id": "dry_run_123",
    "effective_at": "2026-04-23T12:00:00Z",
    "event_data": {
      "amount": 15000,
      "user_id": "user_42",
      "country": "US"
    }
  }'
```

#### Example Response

```json
{
  "transaction_id": "dry_run_123",
  "dry_run": true,
  "skipped_main_rules": false,
  "outcome_counters": {
    "HOLD": 1
  },
  "outcome_set": [
    "HOLD"
  ],
  "resolved_outcome": "HOLD",
  "rule_results": {
    "7": "HOLD"
  },
  "event_version": null,
  "event_version_id": null,
  "evaluation_id": null,
  "evaluation_status": "new",
  "is_current": null,
  "superseded_evaluation_id": null,
  "all_rule_results": {
    "7": "HOLD",
    "8": null
  },
  "evaluated_rules": [
    {
      "r_id": 7,
      "rid": "HIGH_AMOUNT",
      "description": "Hold high amount transactions",
      "evaluation_lane": "main",
      "outcome": "HOLD",
      "matched": true
    }
  ]
}
```

`event_version`, `event_version_id`, and `evaluation_id` are always `null` for dry runs.

#### Status Codes

| Status | Meaning |
|---|---|
| `200` | Evaluation completed |
| `400` | Required field validation failed, strict field lookup failed, or field type casting failed |
| `401` | Missing, invalid, or revoked credentials |
| `413` | Request body exceeds the configured size limit (default 1 MB) |
| `422` | Invalid request payload (schema/validation error) |
| `500` | Evaluation failed during execution/storage |

#### Example Error Bodies

Unauthenticated (`401`):

```json
{
  "detail": "Authentication required"
}
```

Body too large (`413`):

```json
{
  "detail": "Request body too large"
}
```

Validation error (`422`):

```json
{
  "detail": [
    {
      "type": "missing",
      "loc": ["body", "transaction_id"],
      "msg": "Field required",
      "input": {
        "effective_at": "2026-04-23T12:00:00Z",
        "event_data": {"amount": 100}
      }
    }
  ]
}
```

Evaluation/storage error (`500`):

```json
{
  "detail": "Evaluation failed"
}
```

## Live API Documentation (Recommended)

--8<-- "snippets/openapi-links.md"

Use these as the source of truth for request/response models and status codes.
