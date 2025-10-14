# Monitoring & Analytics

Monitor rule activity and labeling trends through the manager application and REST APIs.

---

## Dashboard Overview

Open **Dashboard** in the web UI to review the current state of the system.

- **Active Rules** – Total number of rules deployed for the active organisation.
- **Transaction Volume** – Line chart of events stored in `testing_record_log`, grouped by a selectable time window.
- **Outcome Trends** – Per-outcome lines that show how often each decision was produced over the selected window.

### Available Aggregations

Choose one of the built-in presets to update every chart:

- **1 hour**
- **6 hours**
- **12 hours**
- **24 hours**
- **30 days**

### Working with the Charts

- Spikes or drops in the transaction series can highlight ingestion issues or abnormal traffic.
- Compare outcome lines to understand which rules drive most of the decisions.
- Switch between aggregations to zoom into an incident or to review longer-term trends.

---

## Label Analytics

Select **Label Analytics** from the sidebar to focus on ground-truth labels.

- **Total Labeled Events** – Metric card showing how many stored events carry a label (`testing_record_log.el_id`).
- **Labels Over Time** – One chart per label name with the same aggregation control as the dashboard.
- Use the **Upload Labels** page or the `/mark-event` API to feed data into these views.

---

## API Endpoints

The dashboard fetches its data from JSON endpoints that you can also call directly.

- `GET /api/transaction_volume?aggregation=6h`
  ```json
  {
    "aggregation": "6h",
    "labels": ["2025-01-09 10:00"],
    "data": [120]
  }
  ```
- `GET /api/outcomes_distribution?aggregation=24h`
  ```json
  {
    "aggregation": "24h",
    "labels": ["2025-01-09 10:00", "2025-01-09 11:00"],
    "datasets": [
      {"label": "APPROVE", "data": [8, 6], "borderColor": "rgb(54, 162, 235)"},
      {"label": "REVIEW", "data": [3, 2], "borderColor": "rgb(255, 99, 132)"}
    ]
  }
  ```
- `GET /api/labels_summary`
  ```json
  {
    "total_labeled": 42,
    "pie_chart": {
      "labels": ["FRAUD", "NORMAL"],
      "data": [12, 30],
      "backgroundColor": ["rgb(255, 99, 132)", "rgb(54, 162, 235)"]
    }
  }
  ```
- `GET /api/labels_distribution?aggregation=6h`
  ```json
  {
    "aggregation": "6h",
    "labels": ["2025-01-09 06:00", "2025-01-09 12:00"],
    "datasets": [
      {"label": "FRAUD", "data": [4, 2]},
      {"label": "NORMAL", "data": [10, 8]}
    ]
  }
  ```

Tip: Responses are structured for Chart.js, so `labels` contains the x-axis values and each dataset contains the y-axis series.

---

## Deeper Analysis

For customised reporting, query the underlying tables directly.

```sql
-- Outcome counts by hour
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
-- Labeled events summary
SELECT el.label, COUNT(*) AS total
FROM testing_record_log tr
JOIN event_labels el ON tr.el_id = el.el_id
GROUP BY el.label;
```

---

## Troubleshooting

- No data in charts? Ensure events are reaching the evaluator, and verify `testing_record_log` contains rows within the selected time window.
- Empty label analytics? Make sure labels exist (`event_labels`) and events are marked via `/mark-event` or the CSV upload page.
- API errors? An invalid `aggregation` parameter returns `400`; valid options are `1h`, `6h`, `12h`, `24h`, and `30d`.

For additional help, open an issue on [GitHub](https://github.com/sofeikov/ezrules/issues).
