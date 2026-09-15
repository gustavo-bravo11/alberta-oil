# Keystone Throughput Input Contract

> **Status:** Draft  
> **Owner:** Gustavo Bravo  
> **Last reviewed:** 2026-09-14

## Purpose

This contract defines the data-quality expectations for the CER Keystone throughput and capacity CSV before it enters the pipeline.

## Source and delivery

| Property | Expected value |
| --- | --- |
| Provider | Canada Energy Regulator (CER) |
| Dataset / report | Pipeline Throughput and Capacity Data - Keystone Pipeline |
| File format | CSV |
| Delivery cadence | Monthly |
| Source location | https://open.canada.ca/data/en/dataset/dc343c43-a592-4a27-8ee7-c77df56afb34/resource/b7597d90-0d9a-44d8-8d31-3434d693d6d9 |
| Grain | One record per month, key point, and product; a `total` capacity-summary row is permitted. |

## Required columns and business rules

All columns below must be present in the file. A required column may contain a null value only where its row-level rule permits one.

| Column | Type | Row-level validation rule | Expected / allowed values |
| --- | --- | --- | --- |
| `Date` | date | Valid date; first day of a month; not in the future | `2026-08-01` |
| `Month` | integer | Integer from 1 through 12; must agree with `Date` | `8` |
| `Year` | integer | Four-digit year; must agree with `Date` | `2026` |
| `Company` | string | Non-empty; must equal `South Bow GP (Canada) Ltd.` | `South Bow GP (Canada) Ltd.` |
| `Pipeline` | string | Non-empty; must equal `Keystone pipeline` after trimming | `Keystone pipeline` |
| `Key Point` | string | Non-empty; must equal the Haskett international-boundary key point | `International boundary at or near Haskett, Manitoba` |
| `Latitude` | decimal | Required; within 0 to 90 | `48.9989` |
| `Longitude` | decimal | Required; within -180 to 0 | `-97.9577` |
| `Direction Of Flow` | string | Required for product-flow rows and must be a cardinal direction; no rule on helper rows | `north`; `south`; `east`; `west` |
| `Trade Type` | string | Required for product-flow rows and must be in the shared allowed domain; no rule on helper rows | `import`; `export`; `intracanada`; `intracanada / export` |
| `Product` | string | Must be one of the closed allowed values; blank is permitted only on a helper row | `domestic heavy`; `domestic light`; `domestic light / ngl`; `foreign light`; `refined petroleum products`; `total`; blank on helper rows only |
| `Throughput (1000 m3/d)` | decimal | Required, finite, and non-negative for product-flow rows; no rule on helper rows | `48.75` |
| `Committed Volumes (1000 m3/d)` | decimal | Optional on product-flow rows; no rule on helper rows | `0.0` |
| `Uncommitted Volumes (1000 m3/d)` | decimal | Optional on product-flow rows; no rule on helper rows | `0.0` |
| `Nameplate Capacity (1000 m3/d)` | decimal | Optional on product-flow rows; when present, finite and positive. No rule on helper rows | `123.1` |
| `Available Capacity (1000 m3/d)` | decimal | Required, finite, and positive for product-flow rows; no rule on helper rows | `88.35` |
| `Reason For Variance` | string | Optional; when present, non-empty after trimming | `NEB/REGULATORY DIRECTIVE` |

### Row types

- A **product-flow row** has a product other than `total`. Its direction, trade type, and throughput fields must be populated.
- A **capacity-summary helper row** has `Product` equal to `total` or blank. No field-level validation is applied to helper rows at this time.

## Uniqueness

One record is uniquely identified by:

```text
Date + Pipeline + Key Point + Product
```

Reassess this key when the source grain changes.

## Batch-level checks

- The file is present, readable, and not empty.
- All required columns are present, with no unexpected duplicate headers.
- The batch has no duplicate unique keys.
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
| Duplicate unique key | Error | Quarantine affected rows or stop the batch, depending on scope. |
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
| 2026-09-14 | Initial draft, aligned to the current Keystone raw CSV. | Gustavo Bravo |
| 2026-09-14 | Adopted the shared closed product domain across all pipeline contracts; blank products are allowed only on helper rows. | Gustavo Bravo |
| 2026-09-14 | Broadened the direction domain to all four cardinal directions. | Gustavo Bravo |
| 2026-09-14 | Adopted the shared trade-type domain across all pipeline contracts. | Gustavo Bravo |
| 2026-09-14 | Exempted helper rows from field-level validation pending a later decision on their use. | Gustavo Bravo |
| 2026-09-14 | Changed the batch warning to trigger on any row-count decrease; only an empty file stops the batch on row-count grounds. | Gustavo Bravo |
