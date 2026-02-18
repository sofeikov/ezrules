# Creating Rules

Use this guide when you want to add or tune production rules safely.

## Goal

You will:

1. write a rule that returns an allowed outcome
2. test it with realistic payloads
3. validate it before rollout

## Before You Start

- You can access **Rules** and **Outcomes**
- The outcome names you plan to return already exist (for example `HOLD`, `RELEASE`, `CANCEL`)
- You have sample payloads that represent normal and suspicious behavior

---

## Step 1: Start With a Minimal Rule

Rules are Python-like snippets.
If a condition is met, return an allowed outcome string.

```python
if $amount > 10000:
    return 'HOLD'
```

Notes:

- Use `$field_name` to read event fields (for example `$amount`, `$country`)
- If no condition matches, return nothing

Checkpoint:

- The rule saves without syntax errors
- The returned outcome exists in **Outcomes**

---

## Step 2: Test in the UI First

1. Open the rule in **Rules**
2. Use the **Test Rule** panel
3. Paste realistic JSON payloads
4. Run at least:
   - one payload that should trigger
   - one payload that should not trigger

!!! tip "Type casting in Test Rule"
    The **Test Rule** panel applies the same field type casting as live evaluation. If you have configured field types (under **Settings → Field Types**), values will be cast before the rule runs. Test JSON also contributes to field observations, helping you discover which types your fields carry.
    See [Field Type Management](field-types.md) for details.

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

## Step 3: Pick the Right Pattern

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

## Step 4: Avoid Common Mistakes

- Returning an outcome that is not configured in **Outcomes**
- Using field names that do not exist in event payloads
- Packing too many unrelated conditions into one rule
- Running expensive lookups per event inside rule logic

Use lists (`@list_name`) and precomputed signals where possible.

---

## Step 5: Pre-Deployment Validation

Before enabling major rule changes:

1. Run UI tests with realistic payloads
2. Compare triggered vs non-triggered examples
3. Backtest against historical traffic if available
4. Review potential false-positive impact with analysts
5. Confirm observability:
   - outcome trends visible in **Dashboard**
   - label feedback visible in **Analytics**

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

You can also generate sample data:

```bash
uv run ezrules generate-random-data --n-events 100
```

For broader incident diagnostics, use [Troubleshooting](../troubleshooting.md).

---

## Next Steps

- **[Field Type Management](field-types.md)** - ensure fields are compared with the right types
- **[Labels and Lists](labels-and-lists.md)** - tune decision quality with labels and reusable lists
- **[Analyst Guide](analyst-guide.md)** - end-to-end analyst workflow
- **[Monitoring & Analytics](monitoring.md)** - validate production behavior
