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
- Returns `True` to trigger an outcome
- Returns `False` to pass without action

### Simple Amount-Based Rule

```python
# Flag high-value transactions
if event.get('amount', 0) > 10000:
    return True
return False
```

### Geographic Risk Rule

```python
# Flag transactions from high-risk countries
high_risk_countries = ['XX', 'YY', 'ZZ']
if event.get('country') in high_risk_countries:
    return True
return False
```

### Velocity Rule

```python
# Flag users with too many transactions in short time
user_id = event.get('user_id')
recent_events = count_user_events(user_id, hours=1)

if recent_events > 10:
    return True
return False
```

### Multi-Factor Rule

```python
# Combine multiple risk factors
amount = event.get('amount', 0)
country = event.get('country')
is_new_user = event.get('account_age_days', 0) < 30

risk_score = 0

if amount > 5000:
    risk_score += 2
if country in high_risk_countries:
    risk_score += 3
if is_new_user:
    risk_score += 1

# Trigger if risk score exceeds threshold
if risk_score >= 4:
    return True
return False
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

1. Open your rule in the web interface
2. Find the **Outcomes** section
3. Select which outcomes to trigger
4. A rule can trigger multiple outcomes

---

## Analyzing Results

### Reviewing Flagged Transactions

1. Navigate to **Outcomes** in the sidebar
2. Click on an outcome to see all triggered events
3. Review event details:
   - Transaction amount, user ID, timestamp
   - Which rules triggered
   - Original event data (JSON)

### Using the Analytics Dashboard

Access **Analytics** to view:

- **Events Over Time**: Transaction volume charts
- **Outcome Distribution**: Which outcomes fire most frequently
- **Rule Performance**: Hit rates for each rule
- **Time Range Selection**: 1h, 6h, 12h, 24h, 30d views

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

**Single Transaction:**
1. Find the event in an outcome view
2. Click **Label** button
3. Select label: FRAUD, CHARGEBACK, or NORMAL

**Bulk Upload:**
1. Navigate to **Labels → Upload Labels**
2. Upload CSV file (no header row, 2 columns: event_id, label_name):
   ```csv
   txn_001,FRAUD
   txn_002,NORMAL
   txn_003,CHARGEBACK
   ```
3. Review upload summary

### Labeling via API

```bash
curl -X POST http://localhost:9999/mark-event \
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

1. Review flagged transactions in an outcome
2. Label legitimate ones as NORMAL
3. View **Label Analytics** dashboard
4. Compare NORMAL labels in flagged events vs. total NORMAL

**Calculation:**
```
False Positive Rate = NORMAL labels in outcome / Total triggered events
```

### Measuring False Negatives

False negatives are fraud cases your rules missed.

**Steps to identify:**

1. Label known fraud cases as FRAUD
2. Check if those events triggered relevant outcomes
3. View events NOT in outcomes but labeled FRAUD

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
if event.get('amount', 0) > 50000:
    return True  # Always flag
elif event.get('amount', 0) > 10000:
    # Additional checks for medium amounts
    if event.get('is_international'):
        return True
return False
```

### Time-Based Rules

```python
# Flag unusual transaction times
import datetime
hour = event.get('hour', datetime.datetime.now().hour)

# Flag transactions between 2 AM and 5 AM
if 2 <= hour <= 5:
    return True
return False
```

### User Behavior Rules

```python
# Flag deviation from normal behavior
user_avg_amount = get_user_average(event['user_id'])
current_amount = event.get('amount', 0)

# Flag if 5x normal spending
if current_amount > user_avg_amount * 5:
    return True
return False
```

### List-Based Rules

```python
# Check against blocklists
blocked_users = load_blocklist()
if event.get('user_id') in blocked_users:
    return True

# Check against allowlists (inverse)
trusted_users = load_allowlist()
if event.get('user_id') not in trusted_users:
    return True  # Flag non-trusted users for review
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
