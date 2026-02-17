# From Zero to Live Rule Evaluation in 10 Minutes with ezrules

This is the fastest path to prove value with ezrules: create one rule, send one real event, and see a decision come back from the live evaluator.

If you already finished [Installation](../getting-started/installation.md), this walkthrough is designed to take about 10 minutes.

Teams often have a familiar problem: fraud and compliance logic takes too long to validate because rule authoring, API behavior, and analyst tooling are disconnected. You can spend days debating rule ideas before seeing a real decision in a live path.

This guide focuses on a single outcome: prove the full workflow quickly. In one short run, you will create a rule in the UI, evaluate an event through `/api/v2/evaluate`, and confirm the decision path is working end to end. That gives you a concrete artifact for demos, internal buy-in, and faster iteration.

## Minute 0-2: Start the stack

```bash
docker compose up -d
uv run ezrules api --port 8888
```

In a second terminal:

```bash
cd ezrules/frontend
npm install
npm start
```

Quick checks:

- API health: `http://localhost:8888/ping`
- Frontend login page: `http://localhost:4200`

## Minute 2-5: Create your first decision rule

1. Log in at `http://localhost:4200`.
2. Open **Rules** and create a new rule with this logic:

```python
if $amount > 10000:
    return 'HOLD'
```

3. Open **Outcomes** and confirm `HOLD` exists.

Tip: `HOLD` is seeded by `init-db`, but confirming it avoids confusion during first runs.

## Minute 5-7: Send a live event to the evaluator

Call the evaluator endpoint:

```bash
curl -X POST http://localhost:8888/api/v2/evaluate \
  -H "Content-Type: application/json" \
  -d '{
    "event_id": "txn_live_001",
    "event_timestamp": 1700000000,
    "event_data": {
      "amount": 15000,
      "user_id": "user_42"
    }
  }'
```

You should get JSON with:

- `rule_results`
- `outcome_counters`
- `outcome_set` (should include `HOLD`)

## Minute 7-9: Validate in the UI

1. Open **Dashboard** to confirm transaction activity.
2. Open the rule detail page and use **Test Rule** to try a low amount (for example, `500`) and compare results.

## Minute 9-10: Tune and rerun

Change the threshold, save, and call `/api/v2/evaluate` again. This quick edit-test-evaluate loop is the core workflow teams use to iterate on fraud and compliance logic without redeploying application code.

## Why this 10-minute flow matters

- You validate the full path: UI authoring -> stored rule config -> live evaluator response.
- You show both analyst and engineering workflows in one short demo.
- You have a concrete artifact to share in release notes, demos, and onboarding.

## Next Steps

- [Quick Start (UI First)](../getting-started/quickstart.md)
- [Integration Quickstart](../getting-started/integration-quickstart.md)
- [Creating Rules](../user-guide/creating-rules.md)
- [Monitoring & Analytics](../user-guide/monitoring.md)
