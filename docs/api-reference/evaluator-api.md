# Evaluator API

The evaluator endpoint is part of the unified FastAPI service.
It executes the active rule set against one event payload and stores results.

## Base URL

`http://localhost:8888`

## Run Locally

--8<-- "snippets/start-api.md"

## Endpoint

### Evaluate Event

`POST /api/v2/evaluate`

Evaluates an event against the current rule configuration and stores evaluation results in the database.

#### Request Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `event_id` | `string` | Yes | Unique event identifier |
| `event_timestamp` | `integer` | Yes | Unix timestamp |
| `event_data` | `object` | Yes | Event payload used by rules (fields accessed via `$field`) |

#### Example Request

```bash
curl -X POST http://localhost:8888/api/v2/evaluate \
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
  "rule_results": {
    "7": "HOLD"
  }
}
```

#### Field Type Casting

Before rules are executed, `event_data` values are cast to their configured types (see [Field Type Management](../user-guide/field-types.md)). Unconfigured fields pass through unchanged.

If a value cannot be cast to the configured type, the request is rejected with `400`:

```json
{
  "detail": "Cannot cast field 'amount' value 'not-a-number' to integer"
}
```

Field observations are also recorded on each successful call, contributing to the **Observed Fields** data visible in the UI.

#### Status Codes

| Status | Meaning |
|---|---|
| `200` | Evaluation completed |
| `400` | Field type casting failed (value incompatible with configured type) |
| `422` | Invalid request payload (schema/validation error) |
| `500` | Evaluation failed during execution/storage |

#### Example Error Bodies

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
  "detail": "Evaluation failed: <error details>"
}
```

## Authentication

`/api/v2/evaluate` is currently intended for internal/service use and does not require user authentication.

For production deployments, restrict this endpoint at the network boundary (API gateway, private network, allowlist, or service mesh policy).

## Live API Documentation (Recommended)

--8<-- "snippets/openapi-links.md"

Use these as the source of truth for request/response models and status codes.
