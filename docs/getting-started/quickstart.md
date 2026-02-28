# Quick Start (UI First)

This quickstart is optimized for first success in the web UI.
For service-to-service flows, use [Integration Quickstart](integration-quickstart.md).

!!! info "Prerequisites"
    Complete [Installation](installation.md) first.

## Success Checklist

By the end of this page, you should have:

- one saved rule
- one allowed outcome used by that rule
- one successful rule test in UI
- chart activity in **Dashboard** or **Analytics**

---

## Step 1: Start Services

=== "Docker (demo or production)"

    If you started with `docker-compose.demo.yml` or `docker-compose.prod.yml`, all services are already running — skip to [Step 2](#step-2-log-in).

    Checkpoint:

    - `http://localhost:8888/ping` responds
    - `http://localhost:4200` loads login page

=== "Development (local processes)"

    Start infrastructure:

    ```bash
    docker compose up -d
    ```

    Start API:

    --8<-- "snippets/start-api.md"

    Start frontend:

    ```bash
    cd ezrules/frontend
    npm install
    npm start
    ```

    Checkpoint:

    - `http://localhost:8888/ping` responds
    - `http://localhost:4200` loads login page

---

## Step 2: Log In

1. Open [http://localhost:4200](http://localhost:4200)
2. Sign in with your created user
3. Confirm sidebar shows: **Dashboard**, **Rules**, **Labels**, **Outcomes**, **Analytics**

---

## Step 3: Create a Rule

1. Open **Rules**
2. Click **New Rule**
3. Create:

```python
if $amount > 10000:
    return 'HOLD'
```

4. Save

Checkpoint:

- Rule appears in rules list
- Rule detail page opens with **Test Rule** panel

---

## Step 4: Ensure Outcome Exists

1. Open **Outcomes**
2. Ensure `HOLD` exists
3. Save any changes

---

## Step 5: Test the Rule in UI

1. Return to the rule detail page
2. In **Test Rule**, paste:

```json
{
  "event_id": "txn_001",
  "event_timestamp": 1700000000,
  "event_data": {
    "amount": 15000,
    "user_id": "user_42"
  }
}
```

3. Run test

Checkpoint:

- Test indicates outcome `HOLD`

---

## Step 6: Add Labels and Verify Analytics

1. Open **Labels**
2. Confirm `FRAUD`, `NORMAL`, `CHARGEBACK` labels exist
3. Open **Analytics**
4. Check total labeled count and trend charts

If your deployment supports CSV upload in the Labels UI, upload a small label file and recheck charts.

---

## Next Steps

- [Analyst Guide](../user-guide/analyst-guide.md)
- [Creating Rules](../user-guide/creating-rules.md)
- [Monitoring & Analytics](../user-guide/monitoring.md)
- [Integration Quickstart](integration-quickstart.md)
- [Troubleshooting](../troubleshooting.md)
