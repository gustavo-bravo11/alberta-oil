# CER Rail Exports Input Contract

> **Status:** Draft  
> **Owner:** Gustavo Bravo  
> **Last reviewed:** 2026-09-14

## Purpose

This contract defines the data-quality expectations for the CER monthly crude-oil-exports-by-rail workbook before it enters the rail transform.

## Source and delivery

| Property | Expected value |
| --- | --- |
| Provider | Canada Energy Regulator (CER) |
| Dataset / report | Canadian Crude Oil Exports by Rail — Monthly Data |
| File format | XLSX |
| Delivery cadence | Monthly |
| Source location | https://www.cer-rec.gc.ca/en/data-analysis/energy-commodities/crude-oil-petroleum-products/statistics/canadian-crude-oil-exports-rail-monthly-data.html |
| Worksheet | `CrudeOilExportsByRail` |
| Table location | Header row 8; columns B:G |
| Source grain | One row per month |

## Report metadata

The worksheet contains a visible update label in the form `Numbers last updated on <date>`. The text before the date is metadata; parse only the date portion as `report_date`.

| Metadata field | Location | Validation rule |
| --- | --- | --- |
| `report_date` | Visible `Numbers last updated on <date>` text in the worksheet | Required; parseable to a date; must be on or after the latest derived rail-data month |
| `report_label` | The full visible update text | Required; must contain `Numbers last updated on` after case and whitespace normalization |

The later transform should retain `report_date` alongside the rail data and append a record to the shared `source_metadata.csv` file containing at least `report_date`, `report_label`, and `latest_data_month` linked to its retrieval `run_id`.

## Required table fields and business rules

The current transform reads the table beginning at header row 8, normalizes header names, and derives a first-of-month date. All numeric data values must be finite and non-negative when present.

| Field | Expected type | Validation rule |
| --- | --- | --- |
| `Year` | integer | Required after forward fill; four-digit year; must agree with the derived month date |
| `Month` | string | Required; must be a full month name after trimming and case normalization |
| `Volume (m3/d)` / normalized `volume_m3_per_day` | decimal | Required; finite and non-negative |

Other columns in B:G are retained as source data but do not currently have separate field-level rules.

## Uniqueness

One record is uniquely identified by:

```text
Year + Month
```

After forward-filling `Year` and normalizing `Month`, one source record must exist per calendar month.

## Batch-level checks

- The file is present, readable, and not empty.
- The configured worksheet exists.
- The visible report label and report date are present and parseable.
- The expected header row and required normalized columns are present, with no duplicates.
- Each data row has a valid derived first-of-month date and no duplicate `Year + Month` key.
- The report date is on or after the latest derived rail-data month.
- A non-empty batch whose row count is lower than the prior comparable extract generates a warning; it does not stop the batch on row-count grounds.

## Failure policy

| Condition | Severity | Pipeline behavior |
| --- | --- | --- |
| File missing, unreadable, empty, worksheet missing, or table location changed | Error | Stop this input path. |
| Report label, report date, or required header missing | Error | Stop this input path. |
| Report date invalid or earlier than the latest rail-data month | Error | Stop this input path. |
| Invalid year, month, derived date, or duplicate month | Error | Quarantine the row and report it. |
| Invalid rail-volume value | Error | Quarantine the row and report it. |
| Row count lower than prior comparable extract | Warning | Continue, but flag for review. |

## Validation report

For every run, retain:

- Source filename or URL and retrieval timestamp.
- Worksheet, detected table location, report label, report date, and latest rail-data month.
- Source date range, total rows received, passed, warned, and rejected.
- Each failed rule and its count.
- A safe sample of failed rows.
- Validation-code and contract versions.

## Change log

| Date | Change | Author |
| --- | --- | --- |
| 2026-09-14 | Initial draft based on the current rail transform. | Gustavo Bravo |
| 2026-09-14 | Added report-date metadata parsing and a date-versus-latest-month validation rule. | Gustavo Bravo |
