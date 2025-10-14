# Guide for Analysts

This guide is for fraud analysts, compliance officers, and data analysts who use ezrules to monitor transactions and analyze patterns.

---

## Your Role

As an analyst, you'll:

- Create and tune business rules to detect fraud or compliance violations
- Monitor outcomes and review flagged transactions
- Label transactions for performance measurement
- Analyze rule effectiveness and reduce false positives
- Generate reports on transaction patterns

---

## Creating Effective Rules

### Rule Basics

Rules in ezrules are Python functions that evaluate transaction data. Each rule:

- Receives an event (transaction) as input
- Returns an allowed outcome string (e.g., `'HOLD'`, `'RELEASE'`, `'CANCEL'`)
- If no action is needed, simply do not return a value (no decision)

### Simple Amount-Based Rule

```python
# Flag high-value transactions
if $amount > 10000:
    return 'HOLD'
```

### Geographic Risk Rule

```python
# Flag transactions from high-risk countries
if $country in @high_risk_countries:
    return 'HOLD'
```

### Velocity Rule

```python
# Flag users with too many transactions in a short time.
# Implement `count_events_for_user` in your own helper module.

if $transactions_last_hour > 10:
    return 'HOLD'
```

### Multi-Factor Rule

```python
# Combine multiple risk factors
risk_score = 0

if $amount > 5000:
    risk_score += 2
if $country in @high_risk_countries:
    risk_score += 3
if $account_age_days < 30:
    risk_score += 1

# Trigger if risk score exceeds threshold
if risk_score >= 4:
    return 'HOLD'
```

---

## Working with Outcomes

### What Are Outcomes?

Outcomes represent actions taken when rules fire:

- **Alerts** - Notify the fraud team
- **Blocks** - Automatically decline transactions
- **Reviews** - Queue for manual review
- **Reports** - Log for compliance

### Creating Outcomes

1. Navigate to **Outcomes** in the sidebar
2. Click **Create New Outcome**
3. Provide:
   - **Name**: Clear, descriptive name (e.g., "High Risk Alert")
   - **Description**: When this outcome should trigger

### Linking Rules to Outcomes

Ensure the names you return in your rules exist in the **Outcomes** list:

1. Open **Outcomes** in the sidebar and add names you plan to return (e.g., `HOLD`, `RELEASE`, `CANCEL`).
2. In your rules, return those strings directly.
3. Multiple rules can produce multiple outcomes for the same event; a single rule should return at most one outcome.

---

## Analyzing Results

### Reviewing Flagged Transactions

1. Capture evaluator responses (`/evaluate`) or run SQL against `testing_results_log` joined with `testing_record_log` to list the events a rule triggered.
2. Inspect those stored payloads to understand why the rule matched and whether it should have.
3. Use the rule detail page to experiment with new logic and, if Celery is configured, submit a backtest for historical comparisons.

### Using the Analytics Dashboard

Open **Dashboard** to view:

- **Active Rules** – Count of deployed rules.
- **Transaction Volume** – Time-series chart of processed events.
- **Outcome Trends** – Per-outcome lines showing how often each decision was produced.
- **Time Range Selection** – 1h, 6h, 12h, 24h, 30d views.

### Interpreting Charts

**High Volume Spikes**: May indicate:
- Normal business patterns (end of month, holidays)
- System issues (duplicate events)
- Actual fraud attacks

**Low Hit Rates**: Could mean:
- Rule is too specific (increase sensitivity)
- Fraud pattern has changed
- Rule is working (fraud prevention)

**High Hit Rates**: May indicate:
- Rule is too broad (increase specificity)
- False positive problem
- Legitimate business activity being flagged

---

## Transaction Labeling

### Why Label Transactions?

Labels help you:

- Measure false positive rates
- Identify false negatives (missed fraud)
- Validate rule changes before deployment
- Build datasets for machine learning models

### Labeling via Web Interface

Use the bulk upload workflow:

1. Navigate to **Labels → Upload Labels**
2. Upload a CSV file (no header row, two columns: `event_id,label_name`)
3. Review the summary of applied labels and any validation errors

### Labeling via API

```bash
curl -X POST http://localhost:8888/mark-event \
  -H "Content-Type: application/json" \
  -d '{
    "event_id": "txn_123",
    "label_name": "FRAUD"
  }'
```

### Built-in Labels

- **FRAUD**: Confirmed or suspected fraudulent transactions
- **CHARGEBACK**: Disputed transactions resulting in chargebacks
- **NORMAL**: Legitimate transactions

---

## Performance Analysis

### Measuring False Positives

False positives occur when legitimate transactions are flagged.

**Steps to measure:**

1. Capture the evaluator responses or query `testing_results_log` to list events flagged by the rule or outcome you are assessing.
2. Label legitimate events as NORMAL using `/mark-event` or the bulk upload page.
3. View the **Label Analytics** dashboard to compare the NORMAL counts against your triggered volume.

**Calculation:**
```
False Positive Rate = NORMAL labels in outcome / Total triggered events
```

### Measuring False Negatives

False negatives are fraud cases your rules missed.

**Steps to identify:**

1. Label known fraud cases as FRAUD.
2. Query `testing_results_log` (joined with `testing_record_log`) to verify whether those events triggered an outcome.
3. Investigate any FRAUD-labelled events that do not appear in the outcome results and adjust rules accordingly.

**To reduce false negatives:**
- Lower rule thresholds
- Add more detection rules
- Analyze missed fraud patterns

### Rule Tuning Workflow

1. **Baseline**: Deploy rule and collect data for 7 days
2. **Measure**: Calculate false positive and false negative rates
3. **Analyze**: Review false positives to understand patterns
4. **Adjust**: Modify rule logic or thresholds
5. **Backtest**: Test changes against historical data
6. **Deploy**: Update rule and monitor for 7 days
7. **Repeat**: Continuously optimize

---

## Best Practices

### Rule Design

!!! tip "Start Conservative"
    Begin with higher thresholds to avoid overwhelming the team. Lower thresholds gradually as you tune.

!!! tip "Combine Signals"
    Use multiple risk factors rather than single indicators for more accurate detection.

!!! tip "Test Before Deploy"
    Use historical data to validate rule effectiveness before going live.

### Labeling Strategy

!!! tip "Label Consistently"
    Establish clear criteria for each label type and document them.

!!! tip "Label Quickly"
    Label transactions within 24-48 hours while context is fresh.

!!! tip "Review Regularly"
    Set aside time weekly to review and label flagged transactions.

### Analysis Workflow

!!! tip "Daily Monitoring"
    Check the analytics dashboard daily for anomalies or spikes.

!!! tip "Weekly Deep Dive"
    Analyze false positive rates and rule performance weekly.

!!! tip "Monthly Review"
    Review all rules monthly to identify opportunities for improvement.

---

## Common Patterns

### Amount-Based Detection

```python
# Tiered thresholds
if $amount > 50000:
    return 'HOLD'  # Always flag
elif $amount > 10000:
    # Additional checks for medium amounts
    if $is_international:
        return 'HOLD'
```

### Time-Based Rules

```python
# Flag unusual transaction times
# Flag transactions between 2 AM and 5 AM
if 2 <= $hour <= 5:
    return 'HOLD'
```

### User Behavior Rules

```python
# Flag deviation from normal behavior

# Flag if 5x normal spending
if $amount > $user_avg_amount * 5:
    return 'HOLD'
```

### List-Based Rules

```python
# Check against blocklists
if $user_id in @blocked_users:
    return 'CANCEL'

# Check against allowlists (inverse)
if $user_id not in @trusted_users:
    return 'HOLD'  # Send for manual review
```

---

## Troubleshooting

### Rule Not Triggering

1. **Check event data**: Ensure the event contains expected fields
2. **Verify rule logic**: Add print statements for debugging
3. **Test with sample data**: Use the data generator

### Too Many False Positives

1. **Increase thresholds**: Make rules more specific
2. **Add exceptions**: Exclude known legitimate patterns
3. **Combine signals**: Require multiple risk factors

### Missed Fraud Cases

1. **Lower thresholds**: Increase sensitivity
2. **Add new rules**: Cover patterns you're seeing
3. **Review false negatives**: Analyze what was missed

---

## Next Steps

- **[Managing Outcomes](managing-outcomes.md)** - Deep dive into outcome configuration
- **[Labels and Lists](labels-and-lists.md)** - Advanced labeling and list management
- **[Monitoring & Analytics](monitoring.md)** - Comprehensive analytics guide
- **[Admin Guide](admin-guide.md)** - Learn about user management and permissions
