# Manager Service Reference

The manager service powers the web console and exposes a small set of JSON endpoints used by the dashboard views.

**Base URL:** `http://localhost:8888`

---

## Authentication

The manager uses Flask-Security session-based authentication.

### Login

- **Endpoint:** `POST /login`
- **Body:** form-encoded parameters `email` and `password`
- **Response:** redirect to `/rules` on success; sets a session cookie

For scripted use, perform the login request with a client that preserves cookies (for example, `requests.Session`).

---

## Web Interface Pages

| Page | Endpoint | Description |
|------|----------|-------------|
| Rules list | `GET /rules` | View all rules and navigate to rule details |
| Create rule | `GET /create_rule` | Form for creating a new rule |
| Rule detail | `GET /rule/<int:rule_id>` | Edit a rule, test logic, view revision history |
| Dashboard | `GET /dashboard` | Active rule count, transaction volume, and outcome trend charts |
| Outcomes | `GET /management/outcomes` | Manage allowed outcome names |
| Labels | `GET /management/labels` | Manage available label values |
| Upload labels | `GET /upload_labels` | Bulk label upload via CSV form |
| Label analytics | `GET /label_analytics` | Charts summarising labels over time |
| User lists | `GET /management/lists` | Manage allow/block/watch list entries |
| Audit trail | `GET /audit` | Recent rule and configuration history |
| User management | `GET /user_management` | Manage user accounts |
| Role management | `GET /role_management` | Manage roles and permissions |

All GET routes render HTML templates. Form submissions respond with redirects and flash messages rather than JSON payloads.

---

## JSON APIs

These endpoints back the dashboard charts. Authentication is required (session cookie from `/login`).

### Transaction Volume

- **Endpoint:** `GET /api/transaction_volume`
- **Query Parameters:** `aggregation` (`1h`, `6h`, `12h`, `24h`, `30d`)
- **Response:**
  ```json
  {
    "aggregation": "6h",
    "labels": ["2025-01-09 10:00", "2025-01-09 16:00"],
    "data": [120, 135]
  }
  ```

### Outcome Distribution

- **Endpoint:** `GET /api/outcomes_distribution`
- **Query Parameters:** `aggregation` (`1h`, `6h`, `12h`, `24h`, `30d`)
- **Response:**
  ```json
  {
    "aggregation": "24h",
    "labels": ["2025-01-09 10:00"],
    "datasets": [
      {
        "label": "APPROVE",
        "data": [8],
        "borderColor": "rgb(54, 162, 235)",
        "backgroundColor": "rgba(54, 162, 235, 0.1)"
      },
      {
        "label": "REVIEW",
        "data": [3],
        "borderColor": "rgb(255, 99, 132)",
        "backgroundColor": "rgba(255, 99, 132, 0.1)"
      }
    ]
  }
  ```

### Labels Summary

- **Endpoint:** `GET /api/labels_summary`
- **Response:**
  ```json
  {
    "total_labeled": 42,
    "pie_chart": {
      "labels": ["FRAUD", "NORMAL"],
      "data": [12, 30],
      "backgroundColor": ["rgb(255, 99, 132)", "rgb(54, 162, 235)"]
    }
  }
  ```

### Labels Distribution

- **Endpoint:** `GET /api/labels_distribution`
- **Query Parameters:** `aggregation` (`1h`, `6h`, `12h`, `24h`, `30d`)
- **Response:** same structure as `/api/outcomes_distribution`, but for labels instead of rule outcomes.

---

## Labeling Endpoint

Use the manager API to assign labels to stored events.

- **Endpoint:** `POST /mark-event`
- **Body:** JSON with `event_id` and `label_name`
- **Response:**
  ```json
  {
    "message": "Event 'txn_002' successfully marked with label 'FRAUD'",
    "event_id": "txn_002",
    "label_name": "FRAUD"
  }
  ```

Validation errors return `400` (missing fields), `404` (unknown event or label), or `500` (database error).

---

## Permissions

Access to each endpoint is governed by `PermissionAction` values. The table below summarises the defaults:

| Endpoint | Permission |
|----------|------------|
| `GET /rules`, `GET /dashboard`, `GET /rule/<id>` | `view_rules` |
| `POST /create_rule` | `create_rule` |
| `POST /rule/<id>` | `modify_rule` |
| `GET /management/outcomes` | `view_outcomes` |
| `POST /management/outcomes` | `create_outcome` / `delete_outcome` (per action) |
| `GET /management/labels` | `view_labels` |
| `POST /management/labels` | `create_label` / `delete_label` (per action) |
| `GET /upload_labels` | `view_labels` |
| `POST /upload_labels` | `create_label` (used to upload assignments) |
| `GET /label_analytics` | `view_labels` |
| `GET /management/lists` | `view_lists` |
| `POST /management/lists` | `create_list`, `modify_list`, or `delete_list` based on the submitted action |
| `GET /audit` | `access_audit_trail` |
| `GET /user_management` | `view_users` |
| `POST /user_management` | `create_user` |
| `GET /role_management` | `view_roles` |
| `POST /role_management` | `create_role`, `modify_role`, `delete_role`, or `manage_permissions` |
| `/mark-event` | Accessible without additional permission checks (CSRF exempt) |

---

## Notes

- There are no REST endpoints for creating rules or outcomes programmatically; use the web forms or extend the application.
- The upload forms (`/upload_labels`, `/management/outcomes`, `/management/lists`) respond with HTML redirects, so automated integrations should interact with the JSON APIs listed above instead.
- Webhooks and additional management APIs are not implemented at this time.
