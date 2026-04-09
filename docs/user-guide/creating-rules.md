# Creating Rules

Use this guide when you want to add or tune production rules safely.

## Goal

You will:

1. choose the right rule lane
2. write a rule that returns an allowed outcome
3. test it with realistic payloads
4. validate it before rollout

## Before You Start

- You can access **Rules** and **Outcomes**
- The outcome names you plan to return already exist (for example `HOLD`, `RELEASE`, `CANCEL`)
- You have sample payloads that represent normal and suspicious behavior
- If you plan to use the allowlist lane, you know the currently configured neutral outcome (default `RELEASE`)

---

## Step 1: Choose the Right Rule Lane

Every rule now belongs to one of two lanes:

- **Main rules**: normal decisioning rules that participate in standard outcome resolution
- **Allowlist rules**: rules that short-circuit the main rule set and immediately return the configured neutral outcome when they match

For most fraud/compliance logic, leave the lane as **Main rules**.

Choose **Allowlist rules** only when the rule expresses an explicit trust decision and should stop the rest of the evaluation flow.

See [Allowlist Rules](allowlist-rules.md) for the full rationale and constraints.

---

## Step 2: Start With a Minimal Rule

Rules are Python-like snippets.
If a condition is met, return an allowed outcome string.

```python
if $amount > 10000:
    return 'HOLD'
```

Notes:

- Use `$field_name` to read event fields (for example `$amount`, `$country`)
- If no condition matches, return nothing
- If the rule is in the allowlist lane, it must return the configured neutral outcome

Checkpoint:

- The rule saves without syntax errors
- The returned outcome exists in **Outcomes**

---

## Step 3: Test in the UI First

1. Open the rule in **Rules**
2. Use the **Test Rule** panel
3. Paste realistic JSON payloads
4. Run at least:
   - one payload that should trigger
   - one payload that should not trigger

!!! tip "Type casting in Test Rule"
    The **Test Rule** panel applies the same field type casting as live evaluation. If you have configured field types (under **Settings → Field Types**), values will be cast before the rule runs. Test JSON also contributes to field observations, helping you discover which types your fields carry.
    See [Field Type Management](field-types.md) for details.

!!! tip "Warnings for unseen fields"
    The rule editor warns when your logic references fields that have never been observed in live traffic or rule-test payloads. This does not block saving, but it is a sign that backtests may skip older records that do not contain the new field.

Example payload:

```json
{
  "event_id": "txn_101",
  "event_timestamp": 1700000000,
  "event_data": {
    "amount": 15000,
    "user_id": "user_42"
  }
}
```

Checkpoint:

- Triggering cases produce expected outcome
- Non-triggering cases produce no outcome

---

## Step 4: Pick the Right Pattern

### Threshold pattern

Use when one field is enough to make a decision.

```python
if $amount > 10000:
    return 'HOLD'
```

### List-based pattern

Use when decisioning depends on maintained allow/block lists.

```python
if $user_id in @blocked_users:
    return 'CANCEL'
```

### Allowlist pattern

Use when a match should immediately produce the configured neutral outcome and skip the normal rule set.

```python
if $merchant_id in @trusted_merchants:
    return 'RELEASE'
```

This pattern only makes sense in the **Allowlist rules** lane.

### Multi-signal score pattern

Use when no single field is reliable enough.

```python
risk_score = 0
if $amount > 5000:
    risk_score += 2
if $country in @high_risk_countries:
    risk_score += 2
if $account_age_days < 30:
    risk_score += 1

if risk_score >= 4:
    return 'HOLD'
```

### Time-window pattern

Use when behavior is suspicious only in specific periods.

```python
if 2 <= $hour <= 5 and $amount > 1000:
    return 'HOLD'
```

---

## Step 5: Avoid Common Mistakes

- Returning an outcome that is not configured in **Outcomes**
- Using field names that do not exist in event payloads
- Packing too many unrelated conditions into one rule
- Running expensive lookups per event inside rule logic
- Putting broad trust logic into the allowlist lane when it should still be monitored by the main rule set
- Treating allowlist as a convenience `RELEASE` rule instead of a true short-circuiting policy

Use lists (`@list_name`) and precomputed signals where possible.

---

## Step 6: Pre-Deployment Validation

Before enabling major rule changes:

1. Run UI tests with realistic payloads
2. Compare triggered vs non-triggered examples
3. Backtest against historical traffic if available, and review label-aware precision/recall if your historical events have been labeled
4. Review potential false-positive impact with analysts
5. Confirm observability:
   - outcome trends visible in **Dashboard**
   - label feedback visible in **Analytics**

For higher-stakes changes, add a shadow validation step before promoting to production:

6. Deploy the candidate logic to shadow — either the saved rule version or a draft via the edit panel
7. Allow shadow results to accumulate over a representative traffic window (typically one full business day)
8. Review the shadow vs production outcome comparison in **Shadow Rules** or via `GET /api/v2/shadow/stats`
9. Promote if the outcome distribution matches your intent, or remove and revise if not

Shadow deployment gives you live-traffic validation without any production impact. See [Shadow Deployment](shadow-deployment.md) for the full workflow.

If you want to move beyond observe-only validation, use [Rule Rollouts](rule-rollouts.md) to serve the candidate logic to a controlled percentage of live traffic while the current production version remains the control.

Allowlist rules are different: they are already production behavior. They cannot be sent through shadow or rollout candidate flows.

By default, editing an active rule saves a new `draft` version and removes that rule from live production until you promote it again. If your organisation enables **Settings → General → Auto-promote edits to active rules**, users who also have `PROMOTE_RULES` can save an edit to an active rule and keep it live immediately.

If you need to stop an active rule temporarily without retiring it, use **Pause Rule**. A paused rule is excluded from live production evaluation but stays available for editing and later **Resume Rule** when you want to reactivate it. Pausing requires the dedicated `pause_rules` permission; resuming still requires `promote_rules`.

---

## Review History and Roll Back Safely

If a new rule version performs worse than expected, you do not need to rewrite the old logic by hand.

1. Open the rule and click **Visualize history**.
2. Review the diff timeline to find the last known good revision.
3. Click **Roll back to revision ...** on that historical version.
4. Confirm the dialog after checking the current-to-target diff.

Rollback does **not** delete anything. It creates a brand new `draft` version using the selected historical revision's logic and description, while preserving the full audit trail. If the rule was previously active, promote the new draft after verification to put it back into production.

Use rollback when:

- a recent edit introduced false positives or missed detections
- you need to restore known-good logic quickly during incident response
- you want to recover an older description/logic pair without losing later audit entries

---

## Debugging

If a rule is not behaving as expected:

1. Re-test using the exact payload that failed
2. Verify outcome exists in **Outcomes**
3. Confirm list names/entries referenced in the rule exist
4. Inspect evaluator API response fields:
   - `rule_results`
   - `outcome_counters`
   - `outcome_set`

You can also generate fraud-oriented demo data with familiar transaction fields:

```bash
uv run ezrules generate-random-data --n-events 100
```

For broader incident diagnostics, use [Troubleshooting](../troubleshooting.md).

---

## Next Steps

- **[Field Type Management](field-types.md)** - ensure fields are compared with the right types
- **[Allowlist Rules](allowlist-rules.md)** - when trusted traffic should short-circuit the normal rule set
- **[Labels and Lists](labels-and-lists.md)** - tune decision quality with labels and reusable lists
- **[Analyst Guide](analyst-guide.md)** - end-to-end analyst workflow
- **[Monitoring & Analytics](monitoring.md)** - validate production behavior
