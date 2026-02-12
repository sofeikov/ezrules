# Monitoring & Analytics

Monitoring is where rule quality becomes visible. Use this page for a fast operational check.

You should be able to answer three questions quickly:

- Are events flowing as expected?
- Which outcomes are firing most often?
- Do labels confirm or contradict current rule behavior?

---

## 1) Check Event Flow (Dashboard)

Open **Dashboard** in the sidebar and verify:

- Active rules count is non-zero when rules are deployed
- Transaction volume chart has data in the selected window
- Outcome charts move as you submit test or live events

Use aggregation windows: `1h`, `6h`, `12h`, `24h`, `30d`.

---

## 2) Check Label Feedback (Analytics)

Open **Analytics** in the sidebar and verify:

- Total labeled events
- Label distribution
- Label trends over time

If charts are empty, feed labels through:

- `POST /api/v2/labels/mark-event`
- `POST /api/v2/labels/upload`

---

## 3) Drill Down via API

- `GET /api/v2/analytics/transaction-volume?aggregation=6h`
- `GET /api/v2/analytics/outcomes-distribution?aggregation=24h`
- `GET /api/v2/analytics/labels-summary`
- `GET /api/v2/analytics/labels-distribution?aggregation=6h`

Tip: responses are structured for Chart.js (`labels` + dataset series).

---

## SQL Checks

```sql
SELECT date_trunc('hour', tr.created_at) AS hour,
       trl.rule_result,
       COUNT(*) AS total
FROM testing_results_log trl
JOIN testing_record_log tr ON trl.tl_id = tr.tl_id
WHERE tr.created_at >= NOW() - INTERVAL '7 days'
GROUP BY hour, trl.rule_result
ORDER BY hour;
```

```sql
SELECT el.label, COUNT(*) AS total
FROM testing_record_log tr
JOIN event_labels el ON tr.el_id = el.el_id
GROUP BY el.label;
```

---

## 4) If Something Looks Wrong

Use the central [Troubleshooting Guide](../troubleshooting.md) for symptom -> cause -> fix entries, including:

- API does not start
- Rule does not fire
- Analytics charts are empty
- Backtests stay `PENDING`

For request/response schemas, use OpenAPI docs at `http://localhost:8888/docs`.
