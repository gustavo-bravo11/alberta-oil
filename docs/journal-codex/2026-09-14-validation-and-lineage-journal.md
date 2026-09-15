# Validation and Source-Lineage Journal

Date: 2026-09-14

## What was established

The project now has data-contract documentation for all current CER inputs:

- Enbridge Mainline, Keystone, and Trans Mountain throughput CSVs
- CER estimated production workbook
- CER rail exports workbook

The pipeline-throughput, production, and rail contracts are implemented as validators. Production and rail workbook validators write accepted CSV inputs after removing non-data worksheet rows such as future empty-month placeholders, legends, and notes.

## Validation flow

Pipeline source files follow this intended flow:

```text
downloaded raw file
→ validator
→ data/validated accepted CSV
→ transform
→ transformed analytical output
```

Invalid row-level records are written to `data/quarantine/`; validation reports and row-count history are written to `data/validation/`. The raw download remains the audit copy.

Pipeline stage 1 reads only accepted files from `data/validated/`.

Production and rail transforms now expect these accepted workbook-derived CSVs:

- `data/validated/cer_production_validated.csv`
- `data/validated/cer_rail_validated.csv`

## Orchestration

Run commands from the `project/` directory because that folder is the Python import root:

```powershell
cd project
python -m pipeline.orchestrator full
```

The `full` plan is now:

```text
extract.cer
→ validate.pipeline_inputs
→ transform.pipeline_stage_1
→ transform.pipeline_stage_2
→ validate.workbook_inputs
→ transform.production
→ transform.rail
```

`validate.workbook_inputs` validates both production and rail inputs before their transforms run.

## Run lineage and scheduler handoff

`data/raw/retrieval_log.csv` is the ingestion ledger. New rows will contain:

```text
source_name
raw_filename
date_retrieved_utc
run_id
run_type
```

`run_type` is either `forced` or `scheduled`. Manual invocations default to `forced`. A future scheduler should use:

```powershell
python -m pipeline.orchestrator full --run-type scheduled
```

The orchestrator creates one UUID `run_id` per invocation and passes it to extraction. Historical retrieval-log rows are preserved with blank new fields rather than invented run identities.

The scheduler integration note is in the module docstring of `project/pipeline/orchestrator.py`.

## Shared report metadata

Production and rail report metadata is appended to:

```text
data/transformed/source_metadata.csv
```

Each row is linked to the latest matching retrieval-log entry and includes report metadata plus `run_id` and `run_type` when available.

### Production

- Source worksheet: `HIST - cubic meters per day`
- Report date: cell `A2` in `YYTABLE - cubic meters per day`
- Select the current two-digit-year worksheet first; fall back only to the immediately prior year.
- The current workbook stores `A2` as Excel serial `46261`, which parses to `2026-08-27`.
- The report date must be on or after the latest nonblank historical production month. Current latest month: `2026-06-01`.

### Rail

- Source worksheet: `CrudeOilExportsByRail`
- Parse the visible `Numbers last updated on <date>` text.
- The report date must be on or after the latest derived rail-data month.
- The existing rail fact output retains `source_last_updated`; `source_metadata.csv` is the canonical shared lineage table.

## Production source anomaly

The raw CER production workbook contains a Canada-total reconciliation issue:

- January 2026: `Canada Total` equals the sum of components.
- February through June 2026: `Canada Total` is lower than the component sum by exactly `BC Light`.

The current production transform neither reads `BC Light` nor uses `Canada Total`, so it did not create this discrepancy. The raw workbook’s Canada-total cells are stored values rather than Excel formulas. Treat this as a source anomaly unless CER confirms a methodology change.

The production contract and validator retain both values and emit a reconciliation warning; they do not overwrite or recompute `Canada Total`.

## Validation rules that matter

- All pipeline contracts share closed product, direction, and trade-type domains.
- Pipeline helper rows are identified but currently exempt from field-level validation.
- Any non-empty batch with fewer rows than the previous comparable batch emits a warning; only an empty file stops the batch on row-count grounds.
- Production validates all observed columns, month uniqueness, finite/non-negative metrics, and Canada-total reconciliation.
- Rail validates report metadata, normalized month/year uniqueness, and finite/non-negative rail volume.

## Verification status

Completed successfully using the repository-level `.venv`:

- `python -m compileall -q pipeline`
- `python -m unittest discover -s tests -v` — 4 tests pass
- `python -m pipeline.orchestrator full --run-type scheduled --dry-run`
- `python -m pipeline.validate.workbook_inputs` — production: 318 accepted / 0 rejected; rail: 173 accepted / 0 rejected

## Next steps

1. Add focused tests for production reconciliation, dynamic production-sheet fallback, rail report-label parsing, and scheduled/forced retrieval-log rows.
2. Run `python -m pipeline.orchestrator validate` from `project/` after each refresh and inspect any report warnings or quarantined rows.
3. Review CER’s February 2026 production-total discrepancy with the source publisher before using Canada Total analytically.
4. Add a scheduler that invokes `python -m pipeline.orchestrator full --run-type scheduled`.
