# Evaluator API Reference

The evaluate endpoint is part of the main API service and provides REST APIs for rule evaluation and event submission.

**Base URL:** `http://localhost:8888/api/v2` (default)

!!! note "Unified API Service"
    The evaluator is part of the main FastAPI API service (port 8888). Start it with `uv run ezrules api --port 8888`.

---

## Authentication

Currently, the evaluate endpoint does not require authentication. This is suitable for internal network deployments.

!!! warning "Production Security"
    In production, place the API behind an API gateway with authentication or use network-level access control.

---

## Endpoints

### Ping

Simple connectivity test.

**Endpoint:** `GET /api/v2/ping`

**Response:**
```
OK
```

**Status Codes:**

- `200 OK` - Service is reachable

---

### Evaluate Event

Submit an event for rule evaluation.

**Endpoint:** `POST /api/v2/evaluate`

**Request Body:**
```json
{
  "event_id": "txn_12345",
  "event_timestamp": 1704801000,
  "event_data": {
    "amount": 15000,
    "currency": "USD",
    "user_id": "user_456",
    "merchant_id": "merchant_789",
    "country": "US",
    "metadata": {
      "ip_address": "192.168.1.1",
      "device_id": "device_abc"
    }
  }
}
```

**Required Fields:**
- `event_id` (string) - Unique identifier for this event
- `event_timestamp` (integer) - Unix timestamp
- `event_data` (object) - Event data containing fields your rules evaluate

**Response:**
```json
{
  "event_id": "txn_12345",
  "outcomes": ["High Value Alert", "Manual Review"]
}
```

**Status Codes:**

- `200 OK` - Event processed successfully
- `400 Bad Request` - Invalid request format
- `500 Internal Server Error` - Processing error

**Example:**
```bash
curl -X POST http://localhost:8888/api/v2/evaluate \
  -H "Content-Type: application/json" \
  -d '{
    "event_id": "txn_001",
    "event_timestamp": 1704801000,
    "event_data": {
      "amount": 15000,
      "user_id": "user_123"
    }
  }'
```

---

## Error Handling

### Error Response Format

FastAPI returns standard HTTP error responses. For validation errors:

**Status Codes:**

- `400 Bad Request` - Malformed request body or missing required fields
- `422 Unprocessable Entity` - Request body fails validation
- `500 Internal Server Error` - Rule processing failed or database connectivity issue

---

## Rate Limiting

Currently no rate limiting is enforced. Consider implementing at the API gateway level for production.

**Recommended Limits:**
- 1000 requests/minute per client for production deployments

---

## Example: Python Client

```python
import requests
import time

class EzrulesEvaluatorClient:
    def __init__(self, base_url="http://localhost:8888/api/v2"):
        self.base_url = base_url

    def ping(self):
        response = requests.get(f"{self.base_url}/ping")
        return response.text

    def evaluate(self, event_id, event_data):
        payload = {
            "event_id": event_id,
            "event_timestamp": int(time.time()),
            "event_data": event_data
        }
        response = requests.post(
            f"{self.base_url}/evaluate",
            json=payload
        )
        return response.json()

# Usage
client = EzrulesEvaluatorClient()

# Check service is up
print(client.ping())  # "OK"

# Evaluate an event
result = client.evaluate(
    event_id="txn_123",
    event_data={
        "amount": 15000,
        "user_id": "user_456"
    }
)
print(f"Outcomes: {result['outcomes']}")
```

---

## Next Steps

- **[Analyst Guide](../user-guide/analyst-guide.md)** - Using APIs for analysis
- **[Architecture](../architecture/overview.md)** - System design details
