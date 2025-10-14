# Quick Start

This guide will get you up and running with ezrules in under 10 minutes. You'll create a rule, submit events, and see the results.

!!! info "Prerequisites"
    Make sure you've completed the [Installation Guide](installation.md) before proceeding.

---

## Step 1: Start the Services

Start both the manager and evaluator services in separate terminals:

=== "Terminal 1: Manager Service"

    ```bash
    uv run ezrules manager --port 8888
    ```

    The manager service provides the web interface at [http://localhost:8888](http://localhost:8888)

=== "Terminal 2: Evaluator Service"

    ```bash
    uv run ezrules evaluator --port 9999
    ```

    The evaluator service provides the REST API at [http://localhost:9999](http://localhost:9999)

---

## Step 2: Log In

1. Open your browser to [http://localhost:8888](http://localhost:8888)
2. Log in with the credentials you created during installation
3. You should see the ezrules dashboard

---

## Step 3: Create Your First Rule

Let's create a simple rule to detect high-value transactions.

### Via Web Interface

1. Navigate to **Rules** in the sidebar
2. Click **Create New Rule**
3. Fill in the form:
   - **Name**: `High Value Transaction`
   - **Description**: `Flag transactions over $10,000`
   - **Code**:
     ```python
     if $amount > 10000:
         return 'HOLD'  # Send to manual review
     ```
4. Click **Save**

### What This Rule Does

- Takes an event (transaction) as input
- Checks if the `amount` field is greater than $10,000
- Returns an allowed outcome string (here, `'HOLD'`) to signal a decision; otherwise it returns nothing (no decision)

---

## Step 4: Create an Outcome

Outcomes define what happens when a rule fires.

1. Navigate to **Outcomes** in the sidebar
2. Click **Create New Outcome**
3. Fill in the form:
   - **Name**: `High Value Alert`
   - **Description**: `Alert for high-value transactions`
4. Click **Save**

---

## Step 5: Ensure Outcome Exists

ezrules validates that any literal returned by your rule is an allowed outcome.

1. Navigate to **Outcomes** in the sidebar
2. Ensure `'HOLD'` exists (create it if it doesn't)
3. Save. Your rule now passes the allowed outcomes check

---

## Step 6: Submit Test Events

Now let's send some transactions to see the rule in action.

### Generate Test Data

The easiest way to test is with the built-in data generator:

```bash
uv run ezrules generate-random-data --n-rules 0 --n-events 10
```

This creates 10 random events in the database.

### Or Submit via API

You can also submit events directly via the evaluator API:

```bash
# Low-value transaction (won't trigger rule)
curl -X POST http://localhost:9999/evaluate \
  -H "Content-Type: application/json" \
  -d '{
    "event_id": "txn_001",
    "amount": 500,
    "user_id": "user_123"
  }'

# High-value transaction (will trigger rule)
curl -X POST http://localhost:9999/evaluate \
  -H "Content-Type: application/json" \
  -d '{
    "event_id": "txn_002",
    "amount": 15000,
    "user_id": "user_456"
  }'
```

---

## Step 7: View Results

### In the Web Interface

1. Navigate to **Rules** in the sidebar and open your **High Value Transaction** rule.
2. Use the **Test Rule** panel to replay sample payloads or submit a backtest if Celery is configured.
3. The Outcomes page lists the allowed outcome names; outcome counts and transaction lists are not displayed in the UI yet.

### Inspect the API Response

The evaluator response already tells you which rule fired and what outcomes were produced. Re-run the high-value transaction call:

```bash
curl -X POST http://localhost:9999/evaluate \
  -H "Content-Type: application/json" \
  -d '{
    "event_id": "txn_002",
    "event_timestamp": 1704801000,
    "event_data": {
      "amount": 15000,
      "user_id": "user_456"
    }
  }'
```

Look at the `rule_results`, `outcome_counters`, and `outcome_set` fields in the JSON response to confirm the rule triggered.

### Via Analytics Dashboard

1. Navigate to **Dashboard** in the sidebar.
2. Review the transaction volume chart and the rule outcome trend lines over the selected time range.

---

## Step 8: Label a Transaction

Let's label a transaction as fraud for analytics.

### Via API

```bash
curl -X POST http://localhost:8888/mark-event \
  -H "Content-Type: application/json" \
  -d '{
    "event_id": "txn_002",
    "label_name": "FRAUD"
  }'
```

### Via Web Interface

1. Navigate to **Labels** in the sidebar
2. Click **Upload Labels**
3. Upload a CSV file with format:
   ```csv
   event_id,label_name
   txn_002,FRAUD
   txn_003,NORMAL
   ```

### View Label Analytics

1. Navigate to **Label Analytics** in the sidebar
2. Review the total labeled count and individual label charts
3. Select different time ranges (1h, 6h, 12h, 24h, 30d)

---

## Next Steps

Congratulations! You've successfully:
- ✅ Created a business rule
- ✅ Defined an outcome
- ✅ Submitted events
- ✅ Labeled transactions
- ✅ Viewed analytics

### Learn More

- **[Analyst Guide](../user-guide/analyst-guide.md)** - Learn how to create complex rules and analyze results
- **[Admin Guide](../user-guide/admin-guide.md)** - Manage users, permissions, and system configuration
- **[API Reference](../api-reference/evaluator-api.md)** - Integrate ezrules with your applications
- **[Architecture Overview](../architecture/overview.md)** - Understand how ezrules works

---

## Common Patterns


### Geographic Rules

Flag transactions from unusual locations:

```python
if $user_country in @LatinAmericanCountries:
    return 'HOLD'  # Review LATAM traffic
```

### List-Based Rules

Check against watchlists or blocklists:

```python
if $user_id in @blocklist:
    return 'CANCEL'  # Block known bad actors
```

---

## Tips for Success

!!! tip "Start Simple"
    Begin with simple rules and gradually add complexity as you understand your data patterns.

!!! tip "Test with Historical Data"
    Use the `generate-random-data` command to create realistic test scenarios before deploying rules.

!!! tip "Monitor Performance"
    Check the analytics dashboard regularly to tune your rules and reduce false positives.

!!! tip "Use Labels"
    Label transactions consistently to build a dataset for measuring rule effectiveness.

---

## Troubleshooting

### Rule Not Firing

1. Check the rule syntax in the web interface
2. Verify the event data contains the expected fields
3. Add logging to your rule code for debugging

### Events Not Appearing

1. Ensure the evaluator service is running
2. Check the API response for errors
3. Verify database connectivity

### Slow Performance

1. Add indexes to frequently queried fields
2. Optimize rule code to avoid expensive operations
3. Consider caching for repeated lookups

For more help, see our [GitHub Issues](https://github.com/sofeikov/ezrules/issues).
