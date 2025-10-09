# Managing Outcomes

Outcomes define what happens when rules trigger. This guide covers creating, configuring, and analyzing outcomes.

---

## What Are Outcomes?

Outcomes represent actions or alerts triggered by rules:

- **Alerts** - Notify teams of suspicious activity
- **Blocks** - Automatically decline transactions
- **Reviews** - Queue transactions for manual review
- **Reports** - Log events for compliance

---

## Creating Outcomes

### Via Web Interface

1. Navigate to **Outcomes** in sidebar
2. Click **Create New Outcome**
3. Enter:
   - **Name**: Clear, descriptive (e.g., "High Risk Alert")
   - **Description**: When this should trigger
4. Click **Save**

### Naming Conventions

Good outcome names:
- `High Value Transaction Alert`
- `Suspicious Velocity Block`
- `Manual Review Required`
- `Compliance Report Flag`

---

## Linking Outcomes to Rules

Multiple rules can trigger the same outcome, and one rule can trigger multiple outcomes.

### Link from Rule

1. Open rule in web interface
2. Find **Outcomes** section
3. Select outcomes to trigger
4. Save changes

### Use Cases

**One Rule → Multiple Outcomes:**
```
Rule: "Large International Transfer"
  ↓
Outcomes:
  - Compliance Alert
  - Manual Review
  - Daily Report
```

**Multiple Rules → One Outcome:**
```
Rules:
  - High Amount Rule
  - Velocity Rule
  - Geographic Risk Rule
  ↓
Outcome: "Fraud Alert"
```

---

## Viewing Outcome Data

### Outcome Details Page

1. Navigate to **Outcomes**
2. Click on an outcome
3. View:
   - Total triggered events
   - Recent events list
   - Which rules triggered
   - Event details (JSON)

### Filtering Events

Filter by:
- Date range
- Specific rule
- Event attributes

---

## Analytics

### Outcome Dashboard

Access **Analytics → Outcomes** to see:

- **Trigger Frequency**: How often each outcome fires
- **Trends Over Time**: Historical pattern charts
- **Rule Breakdown**: Which rules contribute most
- **Event Volume**: Total events per outcome

### Performance Metrics

Key metrics to track:

**Hit Rate:**
```
Hit Rate = Events triggering outcome / Total events
```

**False Positive Rate:**
```
FP Rate = NORMAL labels in outcome / Total in outcome
```

**Coverage:**
```
Coverage = Fraud caught / Total fraud (from labels)
```

---

## Best Practices

### Outcome Design

!!! tip "Specific Outcomes"
    Create specific outcomes for different risk types rather than one generic "Alert" outcome.

```
Good:
  - Velocity Alert
  - Geographic Risk Alert
  - High Amount Alert

Not ideal:
  - Generic Alert
```

!!! tip "Severity Levels"
    Use naming to indicate severity:
    - `Critical: ...` - Immediate action
    - `Warning: ...` - Review within 24h
    - `Info: ...` - For reporting only

### Monitoring

Set up regular monitoring:

- **Daily**: Check critical outcomes
- **Weekly**: Review all outcome volumes
- **Monthly**: Analyze false positive rates

---

## Common Patterns

### Tiered Alerting

```
Rules → Outcomes
────────────────
Amount > $50k → Critical Alert
Amount > $10k → Warning Alert
Amount > $5k  → Info Alert
```

### Team Routing

```
Geographic Risk → Regional Fraud Team
Velocity Issues → Operations Team
List Matches    → Compliance Team
```

### Compliance Tracking

```
All Rules → Comprehensive Audit Log
Specific Rules → Regulatory Report Queue
```

---

## Next Steps

- **[Creating Rules](creating-rules.md)** - Write rules that trigger outcomes
- **[Monitoring & Analytics](monitoring.md)** - Detailed analytics guide
- **[Labels and Lists](labels-and-lists.md)** - Enhance detection accuracy
