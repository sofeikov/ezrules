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

Healthy signal:

- transaction volume is non-zero when your integration is sending events
- outcome lines change after rule updates or test submissions

---

## 2) Check Label Feedback (Analytics)

Open **Analytics** in the sidebar and verify:

- Total labeled events
- Label distribution
- Label trends over time

If charts are empty, feed labels through:

- `POST /api/v2/labels/mark-event`
- `POST /api/v2/labels/upload`

Healthy signal:

- `total labeled` increases after marking/uploading labels

---

## 3) Rank Rule Quality (Rule Quality Page)

Open **Rule Quality** in the sidebar and review:

- Best rules (highest average F1)
- Needs attention (lowest average F1)
- Pair metrics table (`outcome -> label`) with precision/recall/F1, TP/FP/FN for configured curated pairs

Tip:

- Increase **Min support** to filter noisy low-volume pairs.
- Use **Lookback days** to constrain query cost and focus on recent behavior.
- Default lookback can be managed under **Settings → General**.
- Rule Quality now loads an async snapshot report and shows **Snapshot as of** timestamp.
- Use **Refresh Report** when you need a newly frozen snapshot immediately.
- Configure curated pairs in **Settings → General** so reports focus only on the mappings your team tracks.
- Use the pair table to decide which outcome-label mapping best represents each rule.

Healthy signal:

- high precision on fraud-related mappings (few false positives)
- high recall on critical labels (few missed fraud labels)

---

## 4) Drill Down via API

- `GET /api/v2/analytics/transaction-volume?aggregation=6h`
- `GET /api/v2/analytics/outcomes-distribution?aggregation=24h`
- `GET /api/v2/analytics/labels-summary`
- `GET /api/v2/analytics/labels-distribution?aggregation=6h`
- `GET /api/v2/analytics/rule-quality?min_support=5&lookback_days=30`
- `POST /api/v2/analytics/rule-quality/reports` then `GET /api/v2/analytics/rule-quality/reports/{report_id}`

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

## 5) Common Symptoms

| Symptom | Likely Cause | Fix |
|---|---|---|
| Dashboard charts are empty | No recent events in selected window | Submit new events and switch aggregation to `24h` |
| Outcome charts empty but volume exists | Rules return no allowed outcomes | Verify rule returns valid outcomes and outcome exists in **Outcomes** |
| Label charts empty | No labels marked/uploaded | Add labels via UI workflow or `POST /api/v2/labels/mark-event` |
| Rule quality page empty | No labeled events or support threshold too high | Label events first, then reduce **Min support** |
| API returns `400` for analytics | Invalid `aggregation` value | Use one of `1h`, `6h`, `12h`, `24h`, `30d` |

For deeper symptom -> cause -> fix entries, use the [Troubleshooting Guide](../troubleshooting.md).
For request/response schemas, use OpenAPI docs at `http://localhost:8888/docs`.
