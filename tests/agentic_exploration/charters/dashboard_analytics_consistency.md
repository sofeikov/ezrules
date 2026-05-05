# Charter: Dashboard Analytics Consistency

## Persona

Risk operations lead using dashboards to understand live rule activity.

## Mission

Explore whether dashboard and analytics numbers match generated traffic and rule outcomes.

## Goals

- Generate known evaluation traffic.
- Compare transaction count, outcome distribution, rule activity, and trend widgets.
- Change date filters or refresh the page.
- Open rule-level analytics if available.
- Compare dashboard numbers with Tested Events.

## Hunt For

- Counts that disagree between dashboard and Tested Events.
- Date filters off by timezone or boundary.
- Paused/deleted rules counted incorrectly.
- Duplicate events counted as new served traffic.
- Empty states shown when data exists.

## Suggested Deterministic Follow-Up

Backend analytics aggregation test or dashboard Playwright E2E.
