# Guide for Analysts

If your job is to review suspicious transactions, tune fraud rules, and explain why a decision was made, this page is for you.

As an analyst, you'll:

- Create and tune business rules to detect fraud or compliance violations
- Monitor outcomes and review flagged transactions
- Label transactions for performance measurement
- Analyze rule effectiveness and reduce false positives
- Build a repeatable workflow your team can trust

---

## The Practical Workflow

Most analyst work in ezrules follows this loop:

1. Create or update a rule.
2. Make sure the outcome your rule returns exists (for example `HOLD`).
3. Test with realistic events.
4. Label results (`FRAUD`, `NORMAL`, `CHARGEBACK`).
5. Check analytics for false positives and missed fraud.
6. Backtest before promoting major rule changes.

This process is simple, but doing it consistently is what improves model quality over time.

---

## Write Rules That Are Easy To Operate

A rule returns an allowed outcome string:

```python
if $amount > 10000:
    return 'HOLD'
```

You will usually get better results by combining multiple signals:

```python
risk_score = 0
if $amount > 5000:
    risk_score += 2
if $country in @high_risk_countries:
    risk_score += 3
if $account_age_days < 30:
    risk_score += 1

if risk_score >= 4:
    return 'HOLD'
```

---

## Test With Realistic Events

For most analysts, the easiest way is to test directly in the UI:

1. Open **Rules** and select your rule.
2. In the right-side **Test Rule** panel, paste a JSON payload in **Test JSON**.
3. Click **Test Rule**.
4. Review the returned reason and rule outcome immediately.

If you need API-based testing for automation, see **Automation Appendix** below.

---

## Label Transactions (This Is Where Quality Comes From)

For most analyst teams, labeling should be a UI workflow first.
Use API labeling only for integrations or batch automation.

### UI workflow (recommended)

1. Open **Labels**.
2. Confirm label names exist (for example `FRAUD`, `NORMAL`, `CHARGEBACK`).
3. If your deployment exposes CSV upload in the UI, upload rows like:

```csv
txn_001,FRAUD
txn_002,NORMAL
```

4. Open **Analytics** and confirm labeled counts/trends update.

API-based labeling options are in **Automation Appendix** below.

Tip: consistent labeling standards are more important than perfect speed.

---

## Measure Analyst Performance Metrics

### False positive rate

`NORMAL labels in triggered outcomes / total triggered events`

### False negative review

1. Mark confirmed fraud as `FRAUD`.
2. Check whether those events produced outcomes.
3. Update rules for patterns that were missed.

---

## Use Dashboard + Analytics Together

Use **Dashboard** and **Analytics** (sidebar label) together for full context:

- transaction volume trends
- outcome trends
- label distribution and label trends

Relevant endpoints:

- `GET /api/v2/analytics/transaction-volume`
- `GET /api/v2/analytics/outcomes-distribution`
- `GET /api/v2/analytics/labels-summary`
- `GET /api/v2/analytics/labels-distribution`

---

## Best Practices

- Start conservative, then tighten thresholds with data.
- Label quickly and consistently with team-agreed definitions.
- Use backtesting for meaningful rule edits.
- Review trends on a fixed cadence (daily/weekly).

---

## Common Rule Patterns

These patterns are good starting points for everyday analyst work.

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

## Next Steps

- **[Creating Rules](creating-rules.md)** - Rule syntax and patterns
- **[Labels and Lists](labels-and-lists.md)** - Labels, lists, and outcomes in one workflow
- **[Monitoring & Analytics](monitoring.md)** - Dashboard metrics

---

## Automation Appendix

Use these API examples only when labeling/testing is integrated into another system.

### Evaluate via API

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

Review:

- `rule_results`
- `outcome_counters`
- `outcome_set`

### Mark one event via API

```bash
curl -X POST http://localhost:8888/api/v2/labels/mark-event \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "event_id": "txn_001",
    "label_name": "FRAUD"
  }'
```

### Upload labels via API

```bash
curl -X POST http://localhost:8888/api/v2/labels/upload \
  -H "Authorization: Bearer <access_token>" \
  -F "file=@labels.csv"
```
