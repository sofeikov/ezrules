# Computed feature math contract

Computed features are deterministic, point-in-time inputs to rule evaluation. This contract defines which historical event versions participate and how each aggregate interprets source values.

## Historical population

For an evaluation at `as_of`, an aggregate window contains event versions whose:

- `effective_at` is greater than or equal to `as_of - window_seconds`;
- `effective_at` is strictly earlier than `as_of`;
- `observed_at` is less than or equal to `as_of`;
- entity key has the same JSON scalar type and value as the evaluated event; and
- transaction version is the version current at `as_of` after applying correction and terminal-state ordering.

The evaluated event itself is therefore excluded. A version effective exactly at the window start is included, while one effective exactly at `as_of` is excluded. Future-effective versions do not replace historical versions before their effective time, even if observed early.

Aggregate entity and filter comparisons are type-sensitive. For example, JSON number `1`, JSON string `"1"`, and JSON boolean `true` are distinct. Entity keys must be non-null JSON scalars. Aggregate filters support scalar `eq` values and scalar members in `in` lists; unsupported container values do not match.

Graph entity links retain their existing textual identity contract for compatibility with persisted graph-link history. Changing graph identity encoding requires a separate migration and backfill.

## Aggregations

| Aggregation | Contract |
|---|---|
| `count` | Number of matched current event versions. Source-field contents do not affect the count. |
| `count_distinct` | Number of distinct non-null JSON scalar source values. JSON types are part of identity; container values are excluded. |
| `sum` | Floating-point sum of eligible numeric values. |
| `avg` | Floating-point sum divided by the number of eligible numeric values. |
| `min` / `max` | Smallest or largest eligible numeric value. |
| `stddev` | Population standard deviation: the square root of the mean squared distance from the population mean. A singleton population returns `0`. |
| `days_since_first_seen` | Whole elapsed UTC days since the earliest matched effective timestamp, floored at zero. |

Numeric inputs include finite JSON numbers and finite numeric strings. JSON booleans, containers, invalid numeric strings, NaN, infinity, and values outside binary floating-point range are excluded and recorded as a feature-resolution warning. Missing or explicit-null source values follow `null_handling`: `exclude` removes them from numeric aggregates, while `zero` contributes `0`. If a mathematically valid aggregate result exceeds the finite binary floating-point range, the value is `null` and the trace records an overflow warning.

When no eligible numeric values remain, numeric aggregates return `null`. Calculations use stable floating-point summation, but the API remains a JSON-number interface. Tests compare results with an independent `Decimal` oracle using explicit tolerances; exact decimal-money arithmetic would require a separate storage and API contract change.

## Corrections and reproducibility

Only one version of a transaction contributes at any `as_of`. A correction replaces the prior version in the aggregate rather than adding a second observation. Late-observed and future-effective versions cannot leak into earlier evaluations.

Feature-resolution traces record the feature version, `as_of`, window start, matched-event count, entity hash, resolution status, and numeric-exclusion warning. Replaying the same event, feature definition, historical ledger, and `as_of` must produce the same value and trace.
