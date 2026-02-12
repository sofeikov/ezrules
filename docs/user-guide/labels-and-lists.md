# Labels, Lists, and Outcomes

Labels, lists, and outcomes work together:

- **Outcomes** are the decisions your rules return (`HOLD`, `RELEASE`, `CANCEL`, and others you define).
- **Labels** are the ground truth you apply later (`FRAUD`, `NORMAL`, `CHARGEBACK`).
- **Lists** are reusable groups referenced in rules (`@blocked_users`, `@trusted_users`, etc.).

If you keep these three clean, your rules become much easier to operate and tune.

---

## Transaction Labels

Labels tell you what actually happened after investigation. They are essential for measuring false positives and false negatives.

### Built-in Labels

- `FRAUD`
- `CHARGEBACK`
- `NORMAL`

### Labeling Methods

#### Single Event via API

```bash
curl -X POST http://localhost:8888/api/v2/labels/mark-event \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "event_id": "txn_123",
    "label_name": "FRAUD"
  }'
```

#### Bulk Upload via CSV

1. Open **Labels -> Upload Labels**.
2. Upload a CSV file with no header row and exactly two columns (`event_id,label_name`).

Example:

```csv
txn_001,FRAUD
txn_002,NORMAL
txn_003,CHARGEBACK
```

---

## Label Analytics

Open **Label Analytics** to view:

- Total labeled events
- Label distribution summary
- Label trends over time
- Aggregation windows (`1h`, `6h`, `12h`, `24h`, `30d`)

---

## Outcomes

Outcomes are your operational decisions. Rules can only return values that exist in the allowed outcomes set.

Common outcomes include:

- `HOLD` for manual review
- `RELEASE` for approve/allow
- `CANCEL` for decline/block

### Why Outcomes Matter

- They standardize decisioning across rules.
- They make outcome trends measurable in analytics.
- They let teams align on operational actions.

### Manage Outcomes in UI

1. Open **Outcomes**.
2. Add outcome names you want rules to return.
3. Remove unused outcomes to keep the set clear.

Example rule snippet:

```python
if $user_id in @blocked_users:
    return 'CANCEL'
```

### Monitor Outcome Trends

Use the Dashboard to track outcome volume over time.

Key analytics endpoint:

- `GET /api/v2/analytics/outcomes-distribution?aggregation=24h`

Supported `aggregation` values: `1h`, `6h`, `12h`, `24h`, `30d`.

### Outcome Best Practices

- Keep outcome names short and stable.
- Reuse existing outcomes where possible.
- Remove unused outcomes during periodic cleanup.
- Validate your outcome set before major rule rollouts.

---

## User Lists

User lists are reusable sets of values referenced from rules with `@ListName`.

Example:

```python
if $user_id in @blocked_users:
    return 'CANCEL'
```

### Manage Lists in UI

1. Open **User Lists**.
2. Create a list.
3. Add or remove entries.

Use clear names and keep list ownership explicit (for example, who updates the list and how often).

---

## How They Work Together

Typical analyst loop:

1. Rule evaluates event and returns an outcome (for example `HOLD`).
2. Analyst reviews flagged transactions.
3. Analyst labels reviewed transactions (`FRAUD` or `NORMAL`).
4. Analytics shows whether current outcomes are too broad or too narrow.
5. Analyst updates list membership and/or rule logic.

This loop is where most quality improvement happens.

---

## API Endpoints

- `POST /api/v2/labels/mark-event`
- `POST /api/v2/labels/upload`
- `GET /api/v2/labels`
- `GET /api/v2/analytics/labels-summary`
- `GET /api/v2/analytics/labels-distribution?aggregation=24h`
- `GET /api/v2/user-lists`
- `GET /api/v2/outcomes`
- `POST /api/v2/outcomes`
- `DELETE /api/v2/outcomes/{outcome_name}`

See OpenAPI docs at `http://localhost:8888/docs` for schemas and auth requirements.

---

## Next Steps

- **[Analyst Guide](analyst-guide.md)** - Analyst workflows
- **[Monitoring & Analytics](monitoring.md)** - Dashboard and metrics
- **[API Reference](../api-reference/manager-api.md)** - API overview
