# Monitoring & Analytics

Monitoring is where rule quality becomes visible. This page helps you answer three questions quickly:

- Are events flowing as expected?
- Which outcomes are firing the most?
- Are labels confirming or contradicting your current rule behavior?

---

## Dashboard

The dashboard provides:

- Active rules count
- Transaction volume over time
- Outcome trends over time
- Aggregation selector (`1h`, `6h`, `12h`, `24h`, `30d`)

---

## Label Analytics

The label analytics view provides:

- Total labeled events
- Label distribution
- Label trends over time

Feed these views by labeling events through:

- `POST /api/v2/labels/mark-event`
- `POST /api/v2/labels/upload`

---

## Analytics API Endpoints

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

## Troubleshooting

- No charts: verify events are being stored in `testing_record_log`.
- Empty outcome series: verify rules are returning allowed outcomes.
- Empty label charts: verify labels exist and events are labeled.
- API `400` on analytics: check `aggregation` value is one of `1h`, `6h`, `12h`, `24h`, `30d`.

For complete request/response schemas, use OpenAPI docs at `http://localhost:8888/docs`.
