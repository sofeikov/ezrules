# Labels and Lists

Learn how to use transaction labels for analytics and user lists for rule execution.

---

## Transaction Labels

### Overview

Labels help you:
- Measure rule performance (false positives/negatives)
- Build training datasets for ML models
- Analyze fraud patterns over time
- Validate rule changes

### Built-in Labels

ezrules includes three standard labels:

- **FRAUD** - Confirmed or suspected fraudulent transactions
- **CHARGEBACK** - Disputed transactions resulting in chargebacks
- **NORMAL** - Legitimate transactions

### Labeling Methods

#### Single Event via API

```bash
curl -X POST http://localhost:9999/mark-event \
  -H "Content-Type: application/json" \
  -d '{
    "event_id": "txn_123",
    "label_name": "FRAUD"
  }'
```

#### Bulk Upload via CSV

1. Navigate to **Labels → Upload Labels**
2. Upload CSV file (no header row, 2 columns: event_id, label_name):

```csv
txn_001,FRAUD
txn_002,NORMAL
txn_003,CHARGEBACK
txn_004,FRAUD
```

3. Review upload summary
4. Labels are applied immediately

#### Via Web Interface

1. Find event in outcome view
2. Click **Label** button
3. Select label type
4. Save

---

## Label Analytics

### Viewing Analytics

Navigate to **Label Analytics** to view:

- **Total Labeled Events**: Coverage metric
- **Labels Over Time**: Individual time-series for each label
- **Distribution**: Breakdown by label type
- **Time Ranges**: 1h, 6h, 12h, 24h, 30d views

### Performance Analysis

#### False Positive Rate

Measure how many legitimate transactions are flagged:

```
False Positives = NORMAL labels in triggered outcomes
False Positive Rate = FP / Total triggered events
```

**Example:**
- 100 events triggered outcome
- 30 labeled as NORMAL
- FP Rate = 30%

#### False Negative Rate

Measure how much fraud is missed:

```
False Negatives = FRAUD labels NOT in outcomes
False Negative Rate = FN / Total FRAUD labels
```

**Example:**
- 50 total FRAUD labels
- 45 triggered outcomes
- 5 missed
- FN Rate = 10%

### Using Labels for Tuning

1. **Baseline**: Run rule for 7 days, label outcomes
2. **Measure**: Calculate FP and FN rates
3. **Adjust**: Modify rule thresholds
4. **Validate**: Test with historical labeled data
5. **Deploy**: Update rule
6. **Monitor**: Track for another 7 days

---

## User Lists

### Overview

User lists store collections of IDs for use in rules:

- **Blocklists** - Known bad actors
- **Allowlists** - Trusted users
- **Watchlists** - Users requiring extra scrutiny
- **VIP Lists** - High-value customers with different thresholds

### Creating Lists

Via web interface:

1. Navigate to **Lists**
2. Click **Create New List**
3. Enter:
   - **Name**: `High Risk Users`
   - **Description**: Purpose of list
4. Add members (user IDs, one per line)
5. Save

### Using Lists in Rules

```python
from ezrules.core.lists import UserList

# Load list
blocklist = UserList.get('high_risk_users')

# Check membership
if event.get('user_id') in blocklist.members:
    return True
```

### Managing Lists

#### Adding Members

```python
# Via API or database
blocklist.add_member('user_12345')
```

#### Removing Members

```python
blocklist.remove_member('user_12345')
```

#### Bulk Operations

Upload CSV file:

```csv
user_id
user_001
user_002
user_003
```

---

## Best Practices

### Labeling

!!! tip "Label Quickly"
    Label transactions within 24-48 hours for best context.

!!! tip "Be Consistent"
    Establish clear criteria for each label type and document them.

!!! tip "Label Everything"
    Label both true positives and false positives for complete analysis.

### Lists

!!! tip "Regular Maintenance"
    Review and update lists weekly to remove stale entries.

!!! tip "Document Purpose"
    Clearly describe each list's purpose and criteria for inclusion.

!!! tip "Version Control"
    Keep history of list changes for audit purposes.

---

## Common Workflows

### Fraud Investigation

1. Rule triggers outcome
2. Analyst reviews transaction
3. If fraud: Label as FRAUD, add to blocklist
4. If legitimate: Label as NORMAL, review rule
5. Update rules based on patterns

### Allowlist Management

1. VIP customer reports false positive
2. Verify customer legitimacy
3. Add to VIP allowlist
4. Update rules to check allowlist
5. Monitor for abuse

### Chargeback Analysis

1. Receive chargeback notification
2. Find original transaction
3. Label as CHARGEBACK
4. Check if rule triggered
5. If missed: Adjust rules
6. Add patterns to detection rules

---

## API Reference

### Label Endpoints

**Mark Single Event:**
```http
POST /mark-event
Content-Type: application/json

{
  "event_id": "txn_123",
  "label_name": "FRAUD"
}
```

**Get Labels Summary:**
```http
GET /api/labels_summary

Response:
{
  "total_labeled": 1500,
  "by_label": {
    "FRAUD": 450,
    "NORMAL": 900,
    "CHARGEBACK": 150
  }
}
```

**Get Labels Distribution:**
```http
GET /api/labels_distribution?period=24h

Response:
{
  "FRAUD": [...],
  "NORMAL": [...],
  "CHARGEBACK": [...]
}
```

---

## Next Steps

- **[Analyst Guide](analyst-guide.md)** - Complete analyst workflows
- **[Monitoring & Analytics](monitoring.md)** - Analytics dashboard
- **[API Reference](../api-reference/evaluator-api.md)** - Full API documentation
