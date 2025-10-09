# Manager API Reference

The Manager service provides the web interface and REST APIs for rule management, user administration, and analytics.

**Base URL:** `http://localhost:8888` (default)

---

## Authentication

The Manager service uses session-based authentication. Users must log in via the web interface before accessing protected endpoints.

### Login

**Endpoint:** `POST /login`

**Request Body:**
```json
{
  "email": "admin@example.com",
  "password": "your-password"
}
```

**Response:**
Sets session cookie for subsequent requests.

**Status Codes:**
- `200 OK` - Login successful, redirects to dashboard
- `401 Unauthorized` - Invalid credentials

---

## Web Interface Pages

### Dashboard

**Endpoint:** `GET /`

Main dashboard showing overview metrics and recent activity.

### Rules Management

**List Rules:** `GET /rules`
- View all business rules
- Search and filter rules
- See rule status (active/inactive)

**Create Rule:** `GET /rules/new`
- Form to create new rule
- Code editor for rule logic

**Edit Rule:** `GET /rules/{rule_id}/edit`
- Modify existing rule
- View rule history

**Rule Details:** `GET /rules/{rule_id}`
- View rule configuration
- See linked outcomes
- Review execution history

### Outcomes Management

**List Outcomes:** `GET /outcomes`
- View all outcomes
- See trigger counts

**Create Outcome:** `GET /outcomes/new`
- Form to create new outcome

**Outcome Details:** `GET /outcomes/{outcome_id}`
- View triggered events
- Analytics for specific outcome

### Labels Management

**Labels Page:** `GET /labels`
- View labeled transactions
- Filter by label type

**Upload Labels:** `GET /upload_labels`
- Bulk upload labels via CSV
- Preview upload results

**Label Analytics:** `GET /label_analytics`
- Time-series charts for labels
- Distribution analysis
- Time range selection (1h, 6h, 12h, 24h, 30d)

### Lists Management

**List User Lists:** `GET /lists`
- View all user lists (blocklists, allowlists, etc.)

**Create List:** `GET /lists/new`
- Form to create new list

**List Details:** `GET /lists/{list_id}`
- View list members
- Add/remove entries

---

## Analytics APIs

These APIs power the analytics dashboards and can be used programmatically.

### Labels Summary

**Endpoint:** `GET /api/labels_summary`

**Response:**
```json
{
  "total_labeled": 1500
}
```

Returns the count of all labeled events.

**Status Codes:**
- `200 OK` - Success

---

### Labels Distribution

**Endpoint:** `GET /api/labels_distribution`

**Query Parameters:**
- `period` (string, optional) - Time period: "1h", "6h", "12h", "24h", "30d"
  - Default: "24h"

**Response:**
```json
{
  "FRAUD": [
    {"time": "2025-01-09T00:00:00Z", "count": 12},
    {"time": "2025-01-09T01:00:00Z", "count": 8}
  ],
  "NORMAL": [...],
  "CHARGEBACK": [...]
}
```

Returns time-series data for each label type within the specified period.

**Status Codes:**
- `200 OK` - Success

**Example:**
```bash
curl "http://localhost:8888/api/labels_distribution?period=24h"
```

---

### Event Volume

**Endpoint:** `GET /api/event_volume`

**Query Parameters:**
- `period` (string, optional) - Time period: "1h", "6h", "12h", "24h", "30d"
  - Default: "24h"

**Response:**
```json
{
  "data": [
    {"time": "2025-01-09T00:00:00Z", "count": 1250},
    {"time": "2025-01-09T01:00:00Z", "count": 980}
  ],
  "total": 25840
}
```

Returns event volume over time.

**Status Codes:**
- `200 OK` - Success

---

### Outcome Statistics

**Endpoint:** `GET /api/outcome_stats`

**Query Parameters:**
- `period` (string, optional) - Time period for statistics

**Response:**
```json
{
  "outcomes": [
    {
      "id": 1,
      "name": "High Value Alert",
      "triggered_count": 245,
      "percentage": 15.2
    },
    {
      "id": 2,
      "name": "Geographic Risk",
      "triggered_count": 123,
      "percentage": 7.6
    }
  ],
  "total_triggered": 1612
}
```

Returns outcome distribution and statistics.

**Status Codes:**
- `200 OK` - Success

---

## Upload Endpoints

### Upload Labels CSV

**Endpoint:** `POST /upload_labels`

**Request:**
- Method: `POST`
- Content-Type: `multipart/form-data`
- Form field: `file` (CSV file)

**CSV Format:**
```csv
event_id,label_name
txn_001,FRAUD
txn_002,NORMAL
txn_003,CHARGEBACK
```

**Response:**
```json
{
  "success": true,
  "uploaded": 3,
  "errors": [],
  "message": "Successfully uploaded 3 labels"
}
```

**Error Response:**
```json
{
  "success": false,
  "uploaded": 2,
  "errors": [
    {"row": 3, "error": "Invalid label name: INVALID"}
  ],
  "message": "Uploaded 2 labels with 1 error"
}
```

**Status Codes:**
- `200 OK` - Upload processed (check response for errors)
- `400 Bad Request` - Invalid file format
- `413 Payload Too Large` - File too large

**Limits:**
- Max file size: 10MB
- Max rows: 10,000

**Example:**
```bash
curl -X POST http://localhost:8888/upload_labels \
  -F "file=@labels.csv"
```

---

### Upload User List CSV

**Endpoint:** `POST /lists/{list_id}/upload`

**Request:**
- Method: `POST`
- Content-Type: `multipart/form-data`
- Form field: `file` (CSV file)

**CSV Format:**
```csv
user_id
user_001
user_002
user_003
```

**Response:**
```json
{
  "success": true,
  "added": 3,
  "message": "Added 3 members to list"
}
```

**Status Codes:**
- `200 OK` - Upload successful
- `400 Bad Request` - Invalid file format
- `404 Not Found` - List doesn't exist

---

## Rule Management APIs

### Create Rule

**Endpoint:** `POST /api/rules`

**Request Body:**
```json
{
  "name": "High Value Transaction",
  "description": "Flag transactions over $10,000",
  "code": "if event.get('amount', 0) > 10000:\n    return True\nreturn False",
  "active": true
}
```

**Response:**
```json
{
  "id": 42,
  "name": "High Value Transaction",
  "created_at": "2025-01-09T10:30:00Z"
}
```

**Status Codes:**
- `201 Created` - Rule created successfully
- `400 Bad Request` - Invalid rule code or parameters

---

### Update Rule

**Endpoint:** `PUT /api/rules/{rule_id}`

**Request Body:**
```json
{
  "name": "Updated Rule Name",
  "code": "# Updated code",
  "active": false
}
```

**Response:**
```json
{
  "id": 42,
  "name": "Updated Rule Name",
  "version": 2,
  "updated_at": "2025-01-09T11:00:00Z"
}
```

**Status Codes:**
- `200 OK` - Rule updated successfully
- `404 Not Found` - Rule doesn't exist
- `400 Bad Request` - Invalid parameters

---

### Delete Rule

**Endpoint:** `DELETE /api/rules/{rule_id}`

**Response:**
```json
{
  "success": true,
  "message": "Rule deleted"
}
```

**Status Codes:**
- `200 OK` - Rule deleted successfully
- `404 Not Found` - Rule doesn't exist

---

## Permissions

Most Manager API endpoints require authentication and specific permissions:

| Endpoint | Permission Required |
|----------|-------------------|
| `GET /rules` | `view_rules` |
| `POST /api/rules` | `create_rule` |
| `PUT /api/rules/{id}` | `modify_rule` |
| `DELETE /api/rules/{id}` | `delete_rule` |
| `GET /outcomes` | `view_outcomes` |
| `POST /api/outcomes` | `create_outcome` |
| `GET /labels` | `view_rules` (any view permission) |
| `POST /upload_labels` | `modify_rule` |

---

## CORS Configuration

For production deployments, configure CORS appropriately:

```python
# config.py
CORS_ALLOWED_ORIGINS = [
    "https://your-frontend.com",
    "https://analytics.company.com"
]
```

---

## Webhooks

Configure webhooks to receive notifications for events:

**Webhook Events:**
- `rule.triggered` - When a rule fires
- `outcome.created` - New outcome triggered
- `label.added` - Transaction labeled

**Webhook Payload:**
```json
{
  "event": "rule.triggered",
  "timestamp": "2025-01-09T10:30:00Z",
  "data": {
    "rule_id": 42,
    "rule_name": "High Value Transaction",
    "event_id": "txn_123",
    "outcomes": ["High Value Alert"]
  }
}
```

---

## Examples

### Python Client

```python
import requests

class EzrulesManager:
    def __init__(self, base_url="http://localhost:8888"):
        self.base_url = base_url
        self.session = requests.Session()

    def login(self, email, password):
        response = self.session.post(
            f"{self.base_url}/login",
            json={"email": email, "password": password}
        )
        return response.status_code == 200

    def get_labels_distribution(self, period="24h"):
        response = self.session.get(
            f"{self.base_url}/api/labels_distribution",
            params={"period": period}
        )
        return response.json()

    def upload_labels(self, csv_file_path):
        with open(csv_file_path, 'rb') as f:
            response = self.session.post(
                f"{self.base_url}/upload_labels",
                files={"file": f}
            )
        return response.json()

# Usage
manager = EzrulesManager()
manager.login("admin@example.com", "password")

# Get analytics
distribution = manager.get_labels_distribution(period="24h")
print(f"FRAUD count: {len(distribution['FRAUD'])}")

# Upload labels
result = manager.upload_labels("labels.csv")
print(f"Uploaded: {result['uploaded']} labels")
```

---

## Next Steps

- **[Evaluator API](evaluator-api.md)** - Rule evaluation API reference
- **[Admin Guide](../user-guide/admin-guide.md)** - Administrative tasks
- **[Configuration](../getting-started/configuration.md)** - Service configuration
