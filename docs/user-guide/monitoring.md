# Monitoring & Analytics

Comprehensive guide to monitoring your rules and analyzing transaction patterns.

---

## Analytics Dashboard

Access the analytics dashboard from the sidebar to view real-time metrics and historical trends.

### Available Views

- **Events Over Time** - Transaction volume charts
- **Outcome Distribution** - Which outcomes fire most frequently
- **Rule Performance** - Execution stats and hit rates
- **Label Analytics** - Time-series for labeled transactions

### Time Range Selection

Choose from multiple time windows:

- **1 hour** - Real-time monitoring
- **6 hours** - Short-term trends
- **12 hours** - Half-day patterns
- **24 hours** - Daily cycles
- **30 days** - Monthly analysis

---

## Key Metrics

### Event Volume

**Total Events:** Overall transaction count
- Monitor for unusual spikes or drops
- Compare to historical baselines
- Identify system issues or business changes

**Events Per Hour:** Throughput metric
- Track system capacity
- Plan scaling decisions
- Identify peak times

### Outcome Metrics

**Trigger Rate:** Percentage of events triggering outcomes

```
Trigger Rate = Events with outcomes / Total events
```

**Typical ranges:**
- Too low (<1%): Rules may be too strict
- Normal (1-5%): Expected for fraud detection
- Too high (>10%): May indicate false positives

**Outcome Distribution:** Which outcomes fire most

Use to:
- Identify most active rules
- Prioritize investigation efforts
- Allocate team resources

### Rule Performance

**Hit Rate per Rule:**
```
Hit Rate = Events triggering rule / Total events
```

**Execution Time:** Average time per rule evaluation
- Target: <100ms per rule
- Monitor for slow rules
- Optimize expensive queries

**Success Rate:** Percentage of successful executions
- Should be >99.9%
- Failures may indicate code errors
- Review error logs for failures

---

## Label Analytics

### Overview Dashboard

Navigate to **Label Analytics** for comprehensive labeling metrics.

### Metrics Available

**Total Labeled Events:** Measures labeling coverage

```
Coverage = Labeled events / Total events
```

Aim for >20% coverage for meaningful analysis.

**Labels Over Time:** Individual time-series charts

View trends for:
- FRAUD labels
- NORMAL labels
- CHARGEBACK labels

**Distribution:** Breakdown by label type

Understand your transaction mix:
- High fraud rate: May need stricter rules
- Low fraud rate: May have effective prevention
- High chargebacks: Customer service issues

### Time Period Analysis

Select different time ranges to identify:

- **Hourly patterns** - Time-of-day fraud trends
- **Daily patterns** - Day-of-week variations
- **Monthly trends** - Long-term fraud evolution

---

## Real-Time Monitoring

### Dashboard Widgets

Key widgets to monitor:

**Recent Events:**
- Last 10-20 events processed
- Current processing rate
- Any errors or warnings

**Active Outcomes:**
- Currently triggered outcomes
- Requiring immediate attention
- Queue depth for manual review

**System Health:**
- Service uptime
- Database connectivity
- API response times

### Alerts

Set up alerts for:

**Volume Anomalies:**
- Event volume drops >50%
- Event volume spikes >200%
- Unusual time-of-day patterns

**Rule Issues:**
- Rule execution failures
- Slow rule execution (>1s)
- High false positive rates

**System Problems:**
- Database connection errors
- API timeouts
- Service crashes

---

## Performance Analysis

### Rule Effectiveness

#### True Positive Rate (Precision)

```
Precision = Correctly flagged fraud / Total flagged
```

Measures accuracy of detections:
- High precision (>70%): Accurate rules
- Low precision (<30%): Too many false positives

#### False Positive Rate

```
FPR = False positives / Total legitimate transactions
```

Target FPR: <5% for most use cases

#### False Negative Rate

```
FNR = Missed fraud / Total fraud
```

Target FNR: <10% for critical fraud

### A/B Testing Rules

Compare rule versions:

1. Deploy new version to 10% of traffic
2. Run for 7 days alongside old version
3. Compare metrics:
   - Hit rate
   - False positive rate
   - False negative rate
4. Roll out winner to 100%

---

## Reporting

### Daily Reports

Generate daily summaries:

```python
# Daily report data
- Total events: 15,000
- Outcomes triggered: 450 (3%)
- Top 3 outcomes:
  1. High Value Alert: 180
  2. Velocity Alert: 150
  3. Geographic Risk: 120
- Labels added: 95
- False positive rate: 4.2%
```

### Weekly Reports

Track trends over week:

- Event volume trends
- Outcome frequency changes
- New fraud patterns identified
- Rule performance changes
- Team productivity metrics

### Monthly Reports

Executive summaries:

- Total fraud prevented (estimated value)
- False positive reduction progress
- System performance metrics
- Staffing recommendations
- Rule optimization opportunities

---

## Best Practices

### Daily Routine

!!! tip "Morning Check"
    - Review overnight outcomes
    - Check for volume anomalies
    - Address critical alerts
    - Label urgent cases

### Weekly Tasks

!!! tip "Performance Review"
    - Analyze false positive rates
    - Review rule effectiveness
    - Update blocklists
    - Plan rule adjustments

### Monthly Activities

!!! tip "Strategic Analysis"
    - Deep-dive analytics review
    - A/B test new rules
    - Archive old data
    - Update documentation

---

## Troubleshooting

### No Data Showing

1. Verify services are running
2. Check date range selection
3. Confirm database connectivity
4. Review browser console for errors

### Slow Dashboard

1. Reduce time range
2. Add database indexes
3. Implement caching
4. Optimize queries

### Missing Events

1. Check evaluator service logs
2. Verify API connectivity
3. Review event submission code
4. Test with sample events

---

## Advanced Analytics

### Custom Queries

Run custom SQL for deeper analysis:

```sql
-- Hourly fraud rate
SELECT
  date_trunc('hour', created_at) as hour,
  COUNT(*) as total_events,
  SUM(CASE WHEN label = 'FRAUD' THEN 1 ELSE 0 END) as fraud_events,
  ROUND(100.0 * SUM(CASE WHEN label = 'FRAUD' THEN 1 ELSE 0 END) / COUNT(*), 2) as fraud_rate
FROM events
WHERE created_at > NOW() - INTERVAL '7 days'
GROUP BY hour
ORDER BY hour DESC;
```

### Export Data

Export for external analysis:

```bash
# Export events to CSV
uv run ezrules export-events --start-date 2025-01-01 --output events.csv

# Export outcomes
uv run ezrules export-outcomes --output outcomes.csv

# Export labels
uv run ezrules export-labels --output labels.csv
```

---

## Next Steps

- **[Analyst Guide](analyst-guide.md)** - Complete analyst workflows
- **[Labels and Lists](labels-and-lists.md)** - Enhance analytics with labels
- **[API Reference](../api-reference/evaluator-api.md)** - Programmatic access
