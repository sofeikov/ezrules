# Field Type Management

Use this guide when you need to ensure event fields are compared with the right data type during rule evaluation.

## Why Field Types Matter

Event payloads arrive as JSON. JSON does not distinguish between `"1000"` (a string) and `1000` (a number). If a rule compares `$amount > 500`, the result depends on whether `amount` is stored as an integer or as a string — and string comparison produces different, often wrong, ordering.

Field type management lets you declare the intended type for each field. ezrules will cast values to that type before rule execution, so comparisons behave as expected. You can also mark a field as required, which makes missing or `null` live events fail fast before any rules run.

---

## How It Works

1. **Observation** — every event that passes through `/api/v2/evaluate` or the **Test Rule** panel records the JSON types it sees for each field. Nested objects are flattened into canonical dotted paths such as `customer.profile.age`. This happens automatically with no configuration.
2. **Configuration** — once you see which types a field carries, you declare its canonical type in **Settings → Field Types** and optionally mark it as **required and non-null**.
3. **Validation + Casting** — at evaluation time, required fields are checked first. Then each configured non-null field value is cast before rule execution. Unconfigured fields pass through unchanged.
4. **Audit** — every create, update, and delete of a field type configuration is recorded in the audit trail.

!!! info "Live observations are eventually consistent"
    Live `/api/v2/evaluate` traffic now buffers field observations to Redis and a periodic Celery drain writes them to Postgres in batches. New live observations can therefore take a few seconds to appear in **Observed Fields**. The **Test Rule** panel still records observations immediately.

---

## Supported Types

| Type | Effect |
|---|---|
| `integer` | `int(value)` |
| `float` | `float(value)` |
| `string` | `str(value)` |
| `boolean` | True for `true`, `1`, `"1"`, `"true"`, `"yes"`, `"on"` (case-insensitive); False otherwise |
| `datetime` | Parsed to `datetime` using the configured format string (Python `strptime` format) |
| `compare_as_is` | No cast; value is used as received |

---

## Opening the Page

1. Log in and open the sidebar.
2. Under **Settings**, click **Field Types**.
3. The page has three sections: **Configure a Field**, **Configured Fields**, and **Observed Fields**.

---

## Configuring a Field Type

### From the Observed Fields table

The fastest way to configure a field is from the **Observed Fields** table, which lists every field and type seen in events so far.

1. Find the row for the field you want to configure.
2. Click **Configure** — the form at the top of the page will be pre-filled with the field name and a suggested type.
3. Adjust the type if needed.
4. If the field must always be present on live events, enable **Required and non-null**.
5. For `datetime`, enter a format string (Python `strptime` notation, for example `%Y-%m-%dT%H:%M:%S`).
6. Click **Save Configuration**.

### Manually

1. Enter the field name in **Field Name** (must match the exact key or dotted nested path used in event payloads).
2. Select the target type.
3. If the field is mandatory for live traffic, enable **Required and non-null**.
4. For `datetime`, fill in the **Datetime Format** field.
5. Click **Save Configuration**.

If a configuration already exists for that field name, it will be updated in place.

---

## Understanding the Observed Fields Table

| Column | Description |
|---|---|
| Field Name | The JSON key or canonical dotted nested path from event payloads |
| Observed Type | The Python type name (`int`, `float`, `str`, `bool`) |
| Configured | Badge shown when a type configuration already exists for this field |

A field may appear in multiple rows if it has been seen with different types (for example `amount: int` and `amount: str`). The same applies to nested paths such as `customer.profile.age`. This indicates data quality issues upstream worth investigating.

!!! tip "Observations from Test Rule"
    Fields observed in the **Test Rule** panel on the Rules page are also recorded. This allows you to build up observations without requiring live traffic.

---

## Editing a Configuration

Configured fields appear in the **Configured Fields** table with their current type, required/optional status, and format. To change a configuration, use the form at the top of the page:

1. Enter (or pre-fill from observations) the same field name.
2. Select the new type.
3. Click **Save Configuration** — the existing configuration is updated.

---

## Deleting a Configuration

In the **Configured Fields** table, click **Delete** next to the field you want to remove. Confirm the prompt.

After deletion, the field reverts to `compare_as_is` behavior — values pass through without casting and are no longer treated as required.

---

## Effect on Rule Evaluation

Once a field is configured, normalization happens before rule execution:

- `/api/v2/evaluate` — required fields are validated first, then values are cast before rules run. If a required field is missing/`null`, or if casting fails (for example a non-numeric string cast to `integer`), the request returns `HTTP 400` with a description of which field failed. Field observations from live traffic are buffered asynchronously, so they may appear shortly after the request succeeds.
- **Test Rule** panel — the same required-field validation and casting rules apply before the rule is tested. Errors are shown inline in the result panel.
- **Event Tester** — the same required-field validation and casting rules apply to full rule-set dry runs, but submitted dry-run payloads do not create field observations.

!!! warning "CastError on invalid values"
    If an event arrives with a value that cannot be cast to the configured type, evaluation will be rejected with an error. Ensure upstream systems send values consistent with the configured types, or use `compare_as_is` to bypass casting.

!!! warning "Required fields are an ingest contract"
    If you enable `required` for a field, live evaluation rejects any event where that field is absent or `null`. Use this only for fields your upstream systems always send.

---

## Audit Trail

All field type configuration changes are logged. To review the history:

1. Open **Audit Trail** in the sidebar.
2. Expand the **Field Type History** section.

Each entry shows: field name, configured type, action (created / updated / deleted), who made the change, and when.

You can also query the API directly:

```bash
GET /api/v2/audit/field-types
GET /api/v2/audit/field-types?field_name=amount
```

---

## API Reference

Field type endpoints require the `Bearer` token and appropriate permissions.

| Method | Path | Permission | Description |
|---|---|---|---|
| `GET` | `/api/v2/field-types` | `VIEW_FIELD_TYPES` | List all configured field types |
| `GET` | `/api/v2/field-types/observations` | `VIEW_FIELD_TYPES` | List all field observations |
| `POST` | `/api/v2/field-types` | `MODIFY_FIELD_TYPES` | Create or update a field type config, including `required` |
| `PUT` | `/api/v2/field-types/{field_name}` | `MODIFY_FIELD_TYPES` | Update an existing config, including `required` |
| `DELETE` | `/api/v2/field-types/{field_name}` | `DELETE_FIELD_TYPE` | Delete a field type config |

### Example: configure a field via API

```bash
curl -X POST http://localhost:8888/api/v2/field-types \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"field_name": "amount", "configured_type": "float", "required": true}'
```

### Example: configure a datetime field

```bash
curl -X POST http://localhost:8888/api/v2/field-types \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"field_name": "event_date", "configured_type": "datetime", "datetime_format": "%Y-%m-%dT%H:%M:%S"}'
```

---

## Next Steps

- **[Creating Rules](creating-rules.md)** — write rules that rely on correctly typed fields
- **[Admin Guide](admin-guide.md)** — permission management for field type access
- **[Troubleshooting](../troubleshooting.md)** — diagnose CastError and evaluation failures
