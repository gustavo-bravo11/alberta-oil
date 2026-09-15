# Enbridge Mainline Throughput Input Contract

> **Status:** Draft  
> **Owner:** Gustavo Bravo  
> **Last reviewed:** 2026-09-14

## Purpose

This contract defines the data-quality expectations for the CER Enbridge Canadian Mainline throughput and capacity CSV before it enters the pipeline.

## Source and delivery

| Property | Expected value |
| --- | --- |
| Provider | Canada Energy Regulator (CER) |
| Dataset / report | Pipeline Throughput and Capacity Data - Enbridge Canadian Mainline |
| File format | CSV |
| Delivery cadence | Monthly |
| Source location | https://open.canada.ca/data/en/dataset/dc343c43-a592-4a27-8ee7-c77df56afb34/resource/a3877960-65f2-47d0-9886-688ba1cabddc |
| Grain | One record per month, key point, product, and trade type; supplemental rows without a product are permitted. |

## Required columns and business rules

All columns below must be present in the file. A required column may contain a null value only where its row-level rule permits one.

| Column | Type | Row-level validation rule | Expected / allowed values |
| --- | --- | --- | --- |
| `Date` | date | Valid date; first day of a month; not in the future | `2026-08-01` |
| `Month` | integer | Integer from 1 through 12; must agree with `Date` | `8` |
| `Year` | integer | Four-digit year; must agree with `Date` | `2026` |
| `Company` | string | Non-empty; must equal `Enbridge Pipelines Inc.` | `Enbridge Pipelines Inc.` |
| `Pipeline` | string | Non-empty; after whitespace normalization, must equal `Enbridge Canadian Mainline system` | `Enbridge Canadian Mainline system` |
| `Key Point` | string | Non-empty after trimming and must contain at least one alphanumeric character | `Into-Sarnia`; `ex-Gretna`; `system` |
| `Latitude` | decimal | On product rows, required and within 0 to 90; no rule on helper rows | `42.953` |
| `Longitude` | decimal | On product rows, required and within -180 to 0; no rule on helper rows | `-82.372` |
| `Direction Of Flow` | string | On product rows, required and must be a cardinal direction; no rule on helper rows | `north`; `south`; `east`; `west` |
| `Trade Type` | string | On product rows, required and in the shared allowed domain; no rule on helper rows | `import`; `export`; `intracanada`; `intracanada / export` |
| `Product` | string | Must be one of the closed allowed values; blank is permitted only on a supplemental row | `domestic heavy`; `domestic light`; `domestic light / ngl`; `foreign light`; `refined petroleum products`; `total`; blank on supplemental rows only |
| `Throughput (1000 m3/d)` | decimal | On product rows, required, finite, and non-negative; no rule on helper rows | `48.75` |
| `Nameplate Capacity (1000 m3/d)` | decimal | On product rows, optional; when present, finite and positive. No rule on helper rows | `123.1` |
| `Available Capacity (1000 m3/d)` | decimal | On product rows, optional; when present, finite and positive. No rule on helper rows | `118.5` |
| `Reason For Variance` | string | Optional; when present, non-empty after trimming | `A` |

### Row types

- A **product-flow row** has a product other than `total`. Its location, direction, trade type, and throughput fields must all be populated.
- A **supplemental helper row** has a blank `Product` or `Product` equal to `total`. `Key Point` remains required; `system` is one valid supplemental key point. No field-level validation is applied to helper rows at this time.
- Whitespace, including embedded line breaks, must be trimmed and normalized before comparisons. The raw `Pipeline` field currently contains an embedded line break.

## Uniqueness

After text normalization, one record is uniquely identified by:

```text
Date + Pipeline + Key Point + Product + Trade Type
```

This includes `Trade Type` because an Enbridge key point can report the same product under more than one trade type in a month. Reassess the key when the source grain changes.

## Batch-level checks

- The file is present, readable, and not empty.
- All required columns are present, with no unexpected duplicate headers.
- The batch has no duplicate normalized unique keys.
- `Month` and `Year` agree with `Date` on every row.
- Values meet the row-type and domain rules above.
- A non-empty batch whose row count is lower than the prior comparable extract generates a warning for review. The batch continues; only an empty file stops it on row-count grounds.

## Failure policy

| Condition | Severity | Pipeline behavior |
| --- | --- | --- |
| File missing, unreadable, or empty | Error | Stop the batch. |
| Required column missing or duplicate | Error | Stop the batch. |
| Invalid date, key, or row-type relationship | Error | Quarantine the row and report it. |
| Invalid numeric or categorical value | Error | Quarantine the row and report it. |
| Duplicate normalized unique key | Error | Quarantine affected rows or stop the batch, depending on scope. |
| Row count lower than the prior comparable extract | Warning | Continue, but flag for review. |

## Validation report

For every run, retain:

- Source filename or URL and retrieval timestamp.
- Contract version and validation-code version.
- Total rows received, passed, warned, and rejected.
- Each failed rule and its count.
- A safe sample of failed rows (without sensitive data).
- The observed date range, row count, and aggregate throughput.

## Change log

| Date | Change | Author |
| --- | --- | --- |
| 2026-09-14 | Reframed from the initial Alberta production / Keystone draft as the Enbridge Mainline throughput input contract; aligned source, schema, grain, nullability, domains, and uniqueness rules to the raw file. | Gustavo Bravo |
| 2026-09-14 | Adopted the shared closed product domain across all pipeline contracts; blank products are allowed only on helper rows. | Gustavo Bravo |
| 2026-09-14 | Broadened the direction domain to all four cardinal directions. | Gustavo Bravo |
| 2026-09-14 | Adopted the shared trade-type domain across all pipeline contracts. | Gustavo Bravo |
| 2026-09-14 | Exempted helper rows from field-level validation pending a later decision on their use. | Gustavo Bravo |
| 2026-09-14 | Replaced the undefined Enbridge key-point reference list with a nonblank alphanumeric-string rule. | Gustavo Bravo |
| 2026-09-14 | Changed the batch warning to trigger on any row-count decrease; only an empty file stops the batch on row-count grounds. | Gustavo Bravo |
