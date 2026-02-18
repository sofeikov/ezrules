# Automatic Field Type Management

JSON doesn't have a strong type system. An `amount` field might arrive as `15000` in one event and `"15000"` in the next, depending on the source system. When a rule does `$amount > 10000`, the result depends entirely on which one shows up — and string comparison produces different ordering than numeric comparison. `"9999" > "10000"` is `True` lexicographically. That's backwards.

The usual fix is to cast inside the rule:

```python
if int($amount) > 10000:
    return 'HOLD'
```

Which works until the next person writes a rule without the cast. Now you have inconsistent behavior across the rule set with no easy way to audit it.

ezrules v0.12 handles this at the engine level.

## How it works

Every event that passes through `/evaluate` is observed. For each field in the payload, we record the JSON type Python saw — `int`, `float`, `str`, `bool` — and how many times we've seen that combination. The same happens in the Test Rule panel, so observations build up during development without needing live traffic.

The observations show up under **Settings → Field Types**:

```
amount    int    1847 observations    last seen 2 minutes ago
amount    str       3 observations    last seen 6 days ago
```

Two rows for `amount` means it arrived with two different types. Three outlier `str` events is a data quality signal worth investigating, but you don't have to wait — configure `amount` as `float` and both variants are handled correctly from that point on.

From the same page, click **Configure** next to any observation, pick the type, save. For datetime fields you also provide a format string (`%Y-%m-%dT%H:%M:%S`), and the value will be parsed into a proper `datetime` object before rules run.

After that, the rule stays as written:

```python
if $amount > 10000:
    return 'HOLD'
```

The comparison is always numeric. No casts inside rules, no special handling per field.

If a value can't be cast — say `amount` is `"not-applicable"` and the configured type is `float` — evaluation returns a `400` with the specific field and value that failed. That's better than a silent wrong answer.

## What this doesn't do

It doesn't fix upstream data quality. If your source sends malformed values you'll find out faster (hard failure rather than incorrect evaluation), but you still have to fix the source.

It's also not a replacement for schema validation at ingestion if you need that. The scope here is making rule comparisons correct without requiring every rule author to remember casting.

## Audit trail

Every field type configuration change is recorded — who changed it, when, and what the previous value was. If `amount` gets changed from `integer` to `float` and evaluation behavior shifts, you can trace it directly. Available at `GET /api/v2/audit/field-types` or in the Audit Trail page under **Field Type History**.

## Full docs

[Field Type Management guide](../user-guide/field-types.md)
