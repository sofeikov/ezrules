# Evaluator API Reference

The Evaluator service provides REST APIs for rule evaluation, event submission, and transaction labeling.

**Base URL:** `http://localhost:9999` (default)

---

## Authentication

Currently, the evaluator API does not require authentication. This is suitable for internal network deployments.

!!! warning "Production Security"
    In production, place the evaluator behind an API gateway with authentication or use network-level access control.

---

## Endpoints

### Health Check

Check if the service is running.

**Endpoint:** `GET /health`

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2025-01-09T10:30:00Z"
}
```

**Status Codes:**
- `200 OK` - Service is healthy
- `503 Service Unavailable` - Service has issues

---

### Ping

Simple connectivity test.

**Endpoint:** `GET /ping`

**Response:**
```
pong
```

**Status Codes:**
- `200 OK` - Service is reachable

---

### Evaluate Event

Submit an event for rule evaluation.

**Endpoint:** `POST /evaluate`

**Request Body:**
```json
{
  "event_id": "txn_12345",
  "amount": 15000,
  "currency": "USD",
  "user_id": "user_456",
  "merchant_id": "merchant_789",
  "country": "US",
  "timestamp": "2025-01-09T10:30:00Z",
  "metadata": {
    "ip_address": "192.168.1.1",
    "device_id": "device_abc"
  }
}
```

**Required Fields:**
- `event_id` (string) - Unique identifier for this event

**Optional Fields:**
- Any additional fields your rules need

**Response:**
```json
{
  "event_id": "txn_12345",
  "rules_triggered": ["High Value Transaction", "Geographic Risk"],
  "outcomes": ["High Value Alert", "Manual Review"],
  "execution_time_ms": 45
}
```

**Status Codes:**
- `200 OK` - Event processed successfully
- `400 Bad Request` - Invalid request format
- `500 Internal Server Error` - Processing error

**Example:**
```bash
curl -X POST http://localhost:9999/evaluate \
  -H "Content-Type: application/json" \
  -d '{
    "event_id": "txn_001",
    "amount": 15000,
    "user_id": "user_123"
  }'
```

---

### Mark Event (Label)

Label a transaction for analytics.

**Endpoint:** `POST /mark-event`

**Request Body:**
```json
{
  "event_id": "txn_12345",
  "label_name": "FRAUD"
}
```

**Parameters:**
- `event_id` (string, required) - Event identifier
- `label_name` (string, required) - Label: FRAUD, CHARGEBACK, or NORMAL

**Response:**
```json
{
  "success": true,
  "event_id": "txn_12345",
  "label_name": "FRAUD",
  "timestamp": "2025-01-09T10:35:00Z"
}
```

**Status Codes:**
- `200 OK` - Label applied successfully
- `400 Bad Request` - Invalid label or event not found
- `500 Internal Server Error` - Labeling error

**Example:**
```bash
curl -X POST http://localhost:9999/mark-event \
  -H "Content-Type: application/json" \
  -d '{
    "event_id": "txn_001",
    "label_name": "FRAUD"
  }'
```

---

### Get Outcomes

Retrieve all outcomes.

**Endpoint:** `GET /api/outcomes`

**Response:**
```json
{
  "outcomes": [
    {
      "id": 1,
      "name": "High Value Alert",
      "description": "Transactions over $10,000",
      "triggered_count": 245
    },
    {
      "id": 2,
      "name": "Geographic Risk",
      "description": "Transactions from high-risk countries",
      "triggered_count": 123
    }
  ]
}
```

**Status Codes:**
- `200 OK` - Success

---

### Get Outcome Details

Retrieve details for a specific outcome.

**Endpoint:** `GET /api/outcomes/{outcome_id}`

**Path Parameters:**
- `outcome_id` (integer) - Outcome identifier

**Response:**
```json
{
  "id": 1,
  "name": "High Value Alert",
  "description": "Transactions over $10,000",
  "triggered_count": 245,
  "recent_events": [
    {
      "event_id": "txn_999",
      "timestamp": "2025-01-09T10:30:00Z",
      "rules": ["High Value Transaction"],
      "data": {...}
    }
  ]
}
```

**Status Codes:**
- `200 OK` - Success
- `404 Not Found` - Outcome doesn't exist

---

### Get Labels Summary

Get summary statistics for labeled transactions.

**Endpoint:** `GET /api/labels_summary`

**Response:**
```json
{
  "total_labeled": 1500,
  "by_label": {
    "FRAUD": 450,
    "NORMAL": 900,
    "CHARGEBACK": 150
  }
}
```

**Status Codes:**
- `200 OK` - Success

---

### Get Labels Distribution

Get time-series data for labels.

**Endpoint:** `GET /api/labels_distribution`

**Query Parameters:**
- `period` (string, optional) - Time period: "1h", "6h", "12h", "24h", "30d"
  - Default: "24h"

**Response:**
```json
{
  "period": "24h",
  "labels": {
    "FRAUD": [
      {"timestamp": "2025-01-09T00:00:00Z", "count": 12},
      {"timestamp": "2025-01-09T01:00:00Z", "count": 8},
      ...
    ],
    "NORMAL": [...],
    "CHARGEBACK": [...]
  }
}
```

**Status Codes:**
- `200 OK` - Success

**Example:**
```bash
curl "http://localhost:9999/api/labels_distribution?period=24h"
```

---

## Batch Operations

### Batch Evaluate

Evaluate multiple events in one request.

**Endpoint:** `POST /evaluate/batch`

**Request Body:**
```json
{
  "events": [
    {
      "event_id": "txn_001",
      "amount": 5000,
      "user_id": "user_1"
    },
    {
      "event_id": "txn_002",
      "amount": 15000,
      "user_id": "user_2"
    }
  ]
}
```

**Response:**
```json
{
  "results": [
    {
      "event_id": "txn_001",
      "outcomes": [],
      "execution_time_ms": 23
    },
    {
      "event_id": "txn_002",
      "outcomes": ["High Value Alert"],
      "execution_time_ms": 45
    }
  ],
  "total_time_ms": 68
}
```

**Limits:**
- Max 100 events per batch
- Max request size: 10MB

---

## Error Handling

### Error Response Format

All errors return a consistent format:

```json
{
  "error": "Invalid request",
  "message": "Missing required field: event_id",
  "code": "INVALID_REQUEST",
  "timestamp": "2025-01-09T10:30:00Z"
}
```

### Common Error Codes

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `INVALID_REQUEST` | 400 | Malformed request body |
| `MISSING_FIELD` | 400 | Required field missing |
| `INVALID_LABEL` | 400 | Unknown label type |
| `EVENT_NOT_FOUND` | 404 | Event doesn't exist |
| `RULE_EXECUTION_ERROR` | 500 | Rule processing failed |
| `DATABASE_ERROR` | 500 | Database connectivity issue |

---

## Rate Limiting

Currently no rate limiting is enforced. Consider implementing at the API gateway level for production.

**Recommended Limits:**
- 1000 requests/minute per client
- 100 events per batch request

---

## Examples

### Complete Workflow

```bash
# 1. Submit event
curl -X POST http://localhost:9999/evaluate \
  -H "Content-Type: application/json" \
  -d '{
    "event_id": "txn_123",
    "amount": 15000,
    "user_id": "user_456"
  }'

# 2. Review outcome
curl http://localhost:9999/api/outcomes/1

# 3. Label as fraud
curl -X POST http://localhost:9999/mark-event \
  -H "Content-Type: application/json" \
  -d '{
    "event_id": "txn_123",
    "label_name": "FRAUD"
  }'

# 4. Check label analytics
curl "http://localhost:9999/api/labels_distribution?period=24h"
```

### Python Client

```python
import requests

class EzrulesClient:
    def __init__(self, base_url="http://localhost:9999"):
        self.base_url = base_url

    def evaluate(self, event_data):
        response = requests.post(
            f"{self.base_url}/evaluate",
            json=event_data
        )
        return response.json()

    def label_event(self, event_id, label_name):
        response = requests.post(
            f"{self.base_url}/mark-event",
            json={
                "event_id": event_id,
                "label_name": label_name
            }
        )
        return response.json()

# Usage
client = EzrulesClient()
result = client.evaluate({
    "event_id": "txn_123",
    "amount": 15000,
    "user_id": "user_456"
})
print(f"Outcomes: {result['outcomes']}")
```

---

## Next Steps

- **[Manager API](manager-api.md)** - Web interface API reference
- **[Analyst Guide](../user-guide/analyst-guide.md)** - Using APIs for analysis
- **[Architecture](../architecture/overview.md)** - System design details
