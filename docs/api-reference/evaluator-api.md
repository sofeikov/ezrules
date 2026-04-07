# Evaluator API

The evaluator endpoint is part of the unified FastAPI service.
It executes the active rule set against one event payload and stores results.

## Base URL

`http://localhost:8888`

## Run Locally

--8<-- "snippets/start-api.md"

## Authentication

`/api/v2/evaluate` requires credentials on every request.
Two methods are accepted:

### API Key (recommended for service-to-service)

Pass the raw key in the `X-API-Key` header:

```bash
curl -X POST http://localhost:8888/api/v2/evaluate \
  -H "X-API-Key: ezrk_<your-key>" \
  -H "Content-Type: application/json" \
  -d '{"event_id": "evt_1", "event_timestamp": 1700000000, "event_data": {}}'
```

API keys are created via `POST /api/v2/api-keys` (requires `MANAGE_API_KEYS` permission).
The raw key is shown **once** at creation time and is never retrievable again.

### Bearer token (for existing user sessions)

Pass a valid JWT access token obtained from `POST /api/v2/auth/login`:

```bash
curl -X POST http://localhost:8888/api/v2/evaluate \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{"event_id": "evt_1", "event_timestamp": 1700000000, "event_data": {}}'
```

## Endpoint

### Evaluate Event

`POST /api/v2/evaluate`

Evaluates an event against the current rule configuration, resolves any conflicting outcomes using the configured outcome hierarchy, and stores evaluation results in the database.

#### Allowlist Short-Circuiting

If one or more active allowlist rules match an event:

- the allowlist result is returned immediately
- the main rule set is skipped for the returned result
- `rule_results` contains the matching allowlist rules only

Allowlist rules must return the configured allowlist outcome. The current runtime setting is `allowlist_match_outcome`, which defaults to `RELEASE`.

#### Request Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `event_id` | `string` | Yes | Unique event identifier |
| `event_timestamp` | `integer` | Yes | Unix timestamp |
| `event_data` | `object` | Yes | Event payload used by rules (fields accessed via `$field`) |

#### Example Request

```bash
curl -X POST http://localhost:8888/api/v2/evaluate \
  -H "X-API-Key: ezrk_<your-key>" \
  -H "Content-Type: application/json" \
  -d '{
    "event_id": "evt_123456",
    "event_timestamp": 1700000000,
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
  "outcome_counters": {
    "HOLD": 1
  },
  "outcome_set": [
    "HOLD"
  ],
  "resolved_outcome": "HOLD",
  "rule_results": {
    "7": "HOLD"
  }
}
```

`resolved_outcome` is the highest-severity outcome after applying the ordering configured under **Settings → Outcome Resolution**.

When allowlist rules match, `resolved_outcome` is derived from the allowlist result and the main rules do not contribute to the returned evaluation.

#### Field Normalization

Before rules are executed, ezrules validates configured required fields and then casts present non-null values to their configured types (see [Field Type Management](../user-guide/field-types.md)). Unconfigured fields pass through unchanged.

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

Field observations are also recorded on each successful call, contributing to the **Observed Fields** data visible in the UI. Live evaluation now buffers those observation writes through Redis and a periodic Celery drain, so observation listings are eventually consistent rather than immediate.

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
      "loc": ["body", "event_id"],
      "msg": "Field required",
      "input": {
        "event_timestamp": 1700000000,
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
