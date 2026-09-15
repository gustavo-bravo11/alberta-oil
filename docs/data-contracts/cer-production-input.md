# CER Estimated Production Input Contract

> **Status:** Draft  
> **Owner:** Gustavo Bravo  
> **Last reviewed:** 2026-09-14

## Purpose

This contract defines the data-quality expectations for the CER estimated Canadian crude oil and equivalent production workbook before it enters the production transform.

## Source and delivery

| Property | Expected value |
| --- | --- |
| Provider | Canada Energy Regulator (CER) |
| Dataset / report | Estimated Production of Canadian Crude Oil and Equivalent |
| File format | XLSX or XLS |
| Delivery cadence | Monthly |
| Source location | https://www.cer-rec.gc.ca/en/data-analysis/energy-commodities/crude-oil-petroleum-products/statistics/estimated-production-canadian-crude-oil-equivalent.html |
| Worksheet | `HIST - cubic meters per day` |
| Source grain | One row per month, with production categories stored in columns |

## Report metadata

The workbook also contains the report-publication date in cell `A2` of its annual cubic-meters-per-day table. This metadata will be parsed into a separate downstream data file; it is not a production-volume row.

### Dynamic worksheet selection

1. Build the current-year worksheet name using the two-digit calendar year: `YYTABLE - cubic meters per day`. For example, in 2026 the preferred worksheet is `26TABLE - cubic meters per day`.
2. If that worksheet is unavailable, use only the immediately preceding year's equivalent: `25TABLE - cubic meters per day` in the 2026 example.
3. If neither worksheet exists, stop this input path with a worksheet-selection error. Do not silently fall back to an older year.

### Metadata validation

| Metadata field | Location | Validation rule |
| --- | --- | --- |
| `report_date` | Cell `A2` of the selected annual worksheet | Required; parseable to a date; must be on or after the latest parsed `Month` in `HIST - cubic meters per day` |
| `report_sheet` | Selected annual worksheet name | Required; must follow the dynamic selection rule above |

The later transform should append this metadata to the shared `source_metadata.csv` file, with at least `report_date`, `report_sheet`, and `latest_data_month` linked to its retrieval `run_id`.

## Required worksheet columns and business rules

All columns below must be present after trimming header whitespace. Production metrics are permitted to be blank when the source does not report a value; when present, they must be finite and non-negative.

| Source field | Type | Validation rule |
| --- | --- | --- |
| `Month` | month label | Required; parseable using `%b-%y`; first day of the parsed month must not be in the future |
| `NL Light` | decimal | Required column; when present, finite and non-negative |
| `NL Heavy` | decimal | Required column; when present, finite and non-negative |
| `ON` | decimal | Required column; when present, finite and non-negative |
| `NB` | decimal | Required column; when present, finite and non-negative |
| `MB` | decimal | Required column; when present, finite and non-negative |
| `NWT` | decimal | Required column; when present, finite and non-negative |
| `SK Light` | decimal | Required column; when present, finite and non-negative |
| `SK Heavy` | decimal | Required column; when present, finite and non-negative |
| `AB Conv Light` | decimal | Required column; when present, finite and non-negative |
| `AB Conv Heavy` | decimal | Required column; when present, finite and non-negative |
| `AB Upgraded` | decimal | Required column; when present, finite and non-negative |
| `AB Non-Upgraded` | decimal | Required column; when present, finite and non-negative |
| `BC Light` | decimal | Required column; when present, finite and non-negative |
| `BC Cond` | decimal | Required column; when present, finite and non-negative |
| `AB Cond` | decimal | Required column; when present, finite and non-negative |
| `NS Cond` | decimal | Required column; when present, finite and non-negative |
| `SK Cond` | decimal | Required column; when present, finite and non-negative |
| `Canada Total` | decimal | Required; finite and non-negative; reconcile against the component sum below |
| `Raw Mined Bitumen` | decimal | Required column; when present, finite and non-negative |
| `Raw In Situ Bitumen` | decimal | Required column; when present, finite and non-negative |

### Canada Total reconciliation

For each row, compare `Canada Total` with the sum of these reported component columns:

```text
NL Light + NL Heavy + ON + NB + MB + NWT + SK Light + SK Heavy
+ AB Conv Light + AB Conv Heavy + AB Upgraded + AB Non-Upgraded
+ BC Light + BC Cond + AB Cond + NS Cond + SK Cond
```

`Raw Mined Bitumen` and `Raw In Situ Bitumen` are excluded because they are supporting source values, not separate components of the reported Canada total.

If the reported total differs from the component sum, retain both values and emit a warning. Do not recompute or overwrite `Canada Total`. The current source exhibits this warning beginning in February 2026, where the difference equals `BC Light`.

## Uniqueness

One record is uniquely identified by:

```text
Month
```

Each monthly source row must be unique after parsing the source month.

## Batch-level checks

- The file is present, readable, and not empty.
- The configured worksheet exists and contains data rows.
- The dynamically selected annual worksheet exists, and its `A2` report date is present and not earlier than the latest historical production month.
- All required columns are present after header trimming, with no duplicate normalized headers.
- Each source month is unique and parseable.
- A non-empty batch whose row count is lower than the prior comparable extract generates a warning; it does not stop the batch on row-count grounds.

## Failure policy

| Condition | Severity | Pipeline behavior |
| --- | --- | --- |
| File missing, unreadable, empty, or worksheet missing | Error | Stop this input path. |
| Current- or prior-year annual worksheet unavailable, or `A2` report date missing / invalid / earlier than the latest production month | Error | Stop this input path. |
| Required column missing or duplicate normalized header | Error | Stop this input path. |
| Invalid month or duplicate month | Error | Quarantine the row and report it. |
| Invalid production metric | Error | Quarantine the row and report it. |
| Reported Canada Total differs from component sum | Warning | Continue, retain source values, and flag for review. |
| Row count lower than prior comparable extract | Warning | Continue, but flag for review. |

## Validation report

For every run, retain:

- Source filename or URL and retrieval timestamp.
- Worksheet name, source date range, and row count.
- Selected annual worksheet, parsed report date, and latest production month used for the date comparison.
- Total rows received, passed, warned, and rejected.
- Each failed rule and its count.
- A safe sample of failed rows.
- The reported Canada Total, calculated component sum, and difference for reconciliation warnings.
- Validation-code and contract versions.

## Change log

| Date | Change | Author |
| --- | --- | --- |
| 2026-09-14 | Initial draft based on the current production transform and raw workbook. | Gustavo Bravo |
| 2026-09-14 | Added all observed production columns and a non-mutating Canada Total reconciliation warning. | Gustavo Bravo |
| 2026-09-14 | Added dynamic annual-worksheet selection and report-date metadata validation. | Gustavo Bravo |
