# Alberta Oil Project Journal

Date: August 26, 2026

## Purpose

This is a working journal for re-orienting myself in the project before writing a proper README.
The goal is to document what exists, what appears to work, what data is being pulled and transformed,
what is not yet integrated, and what the next steps should likely be.

## High-Level Repo State

- The tracked development window in git is concentrated between May 4, 2026 and May 13, 2026.
- The most recent tracked commit is `7c24145` on May 13, 2026: "added a second transformation step to clean the pipeline table, outputs two csv files".
- There is no README in the current project directory.
- There is no test suite in the current project directory.
- There is no dependency manifest checked in here (`requirements.txt`, `pyproject.toml`, `Pipfile`, etc.).
- There is no real load layer yet; `pipeline/load/__init__.py` is empty.
- There is no current orchestrator file or unified CLI entry point in the working tree.
- Raw and transformed data exist locally under `data/`, but they are not tracked by git from this subdirectory view.
- A local virtual environment exists at `alberta-oil-env/`.

## What Is Implemented

### 1. Extraction

File: `pipeline/extract/cer_extract.py`

This is the current raw-data downloader.

It loops through the source definitions in `pipeline/config/sources.py` and downloads:

- CER estimated production workbook
- Enbridge throughput CSV
- Keystone throughput CSV
- Trans Mountain throughput CSV
- CER rail exports workbook

It depends on utility helpers in `pipeline/utils/web_download.py`:

- `safe_request_get()`
- `find_file_url()`
- `download_file()`

The extraction logic is generic and reusable enough for the current sources, but it is still just a script with `main()`. There is no higher-level runner coordinating extract plus transform.

### 2. Pipeline Throughput Transform, Stage 1

Files:

- `pipeline/transform/a_1_em_pipeline_transform.py`
- `pipeline/transform/a_1_ks_pipeline_transform.py`
- `pipeline/transform/a_1_tm_pipeline_transform.py`

These scripts each take one raw pipeline file and split it into two stage-1 outputs:

- a flow/location table for mapping and detailed movement analysis
- a capacity table for utilization analysis

Current stage-1 outputs present locally:

- `data/transformed/throughput_stage_1/enbridge_mainline_flow_location.csv`
- `data/transformed/throughput_stage_1/enbrdige_mainline_capacity.csv`
- `data/transformed/throughput_stage_1/keystone_flow_location.csv`
- `data/transformed/throughput_stage_1/keystone_capacity.csv`
- `data/transformed/throughput_stage_1/transmountain_flow_location.csv`
- `data/transformed/throughput_stage_1/transmountain_capacity.csv`

Notes by pipeline:

- Enbridge:
  - Drops `key_point == system`
  - Filters out rows where `available_capacity_1000_m3_d` is null
  - Uses `ex-Gretna` as the effective capacity basis for the final capacity table
- Keystone:
  - Keeps a detailed flow table
  - Aggregates by `date`, `pipeline`, `key_point` for the capacity output
  - Carries forward `reason_for_variance`
- Trans Mountain:
  - Treats the `system` row as the capacity record
  - Aggregates non-system rows into total flow
  - Builds `capacity_basis` from joined key points such as Burnaby / Sumas / Westridge

All three scripts convert throughput and capacity from thousands of cubic meters per day into:

- cubic meters per day
- barrels per day

using `CUBIC_M_TO_BARRELS = 6.2898`.

### 3. Pipeline Throughput Transform, Stage 2

File: `pipeline/transform/a_2_throughput_standardization.py`

This is the consolidation step.

It reads the stage-1 CSVs, concatenates them, and produces two final outputs:

- `data/transformed/pipeline_flow.csv`
- `data/transformed/pipeline_capacity.csv`

This step standardizes and reshapes fields such as:

- `pipeline`
- `key_point`
- `trade_type`
- `capacity_basis`
- `reason_for_variance`

It also preserves the original text columns beside the standardized versions, which is useful for auditability but is also the source of one of the CSV preview issues documented below.

### 4. Production Transform

File: `pipeline/transform/b_1_production_transform.py`

This script reads the CER production workbook and narrows it to the production categories relevant to the Alberta / Saskatchewan crude story:

- `sk_light`
- `sk_heavy`
- `ab_conv_light`
- `ab_conv_heavy`
- `ab_upgraded`
- `ab_non_upgraded`
- `ab_cond`

It then:

- parses the month field into a date
- unpivots the dataset into long form
- converts cubic meters per day into barrels per day
- assigns a constraint category to each oil type

Current local output:

- `data/transformed/western_canada_estimated_production.csv`

### 5. Rail Transform

File: `pipeline/transform/c_1_rail_transform.py`

This script reads the CER monthly rail export workbook and:

- extracts the sheet region starting at row 8, columns `B:G`
- normalizes the column names
- forward-fills the year
- builds a first-of-month `date`
- computes `volume_barrels_per_day`

Configured output:

- `data/transformed/monthly_rail_exports.csv`

Important current-state note:

- That output file is not present locally right now.
- The script computes `volume_barrels_per_day`, but the final `select()` only writes `date` and `volume_m3_per_day`, so the derived barrels/day value is currently dropped from the final export.

## Local Data Snapshot

### Raw Files Present

- `data/raw/cer_estimated_production_details.xlsx`
- `data/raw/cer_rail_exports_monthly_raw.xlsx`
- `data/raw/enbridge_throughput_details.csv`
- `data/raw/keystone_throughput_details.csv`
- `data/raw/transmountain_throughput_details.csv`

### Transformed Files Present

- `data/transformed/western_canada_estimated_production.csv`
- `data/transformed/pipeline_flow.csv`
- `data/transformed/pipeline_capacity.csv`
- all six stage-1 throughput CSVs listed above

### Expected But Missing Transformed File

- `data/transformed/monthly_rail_exports.csv`

## Data Coverage Observed Locally

### Raw Pipeline Files

- `enbridge_throughput_details.csv`: 2,228 rows, from `2007-01-01` to `2025-12-01`
- `keystone_throughput_details.csv`: 504 rows, from `2010-07-01` to `2025-12-01`
- `transmountain_throughput_details.csv`: 2,385 rows, from `2006-01-01` to `2025-12-01`

### Raw Workbook Coverage

- Production workbook relevant sheet: 324 rows x 21 columns
- Rail workbook extracted region: 170 rows x 6 columns
- The rail raw workbook currently includes data through February 2026 in the sampled rows

### Transformed Outputs

- `western_canada_estimated_production.csv`: 2,189 rows, from `2000-01-01` to `2026-01-01`
- `pipeline_flow.csv`: 4,007 data rows, from `2006-01-01` to `2025-12-01`
- `pipeline_capacity.csv`: 654 data rows, from `2006-01-01` to `2025-12-01`

### Stage-1 Throughput Outputs

- Enbridge flow: 1,490 rows
- Enbridge capacity: 228 rows
- Keystone flow: 372 rows
- Keystone capacity: 186 rows
- Trans Mountain flow: 2,145 rows
- Trans Mountain capacity: 240 rows

## What Data Is Being Manipulated

### Pipeline Data

The pipeline transforms currently manipulate:

- `date`
- `pipeline`
- `key_point`
- `latitude`
- `longitude`
- `direction_of_flow`
- `trade_type`
- `product`
- `throughput`
- `available_capacity`
- `reason_for_variance`

Main transformations:

- column-name normalization
- unit conversion from `1000 m3/d` to `m3/d` and `barrels/d`
- filtering of non-analytic rows like `system` or `total`, depending on the source
- aggregation to create utilization-ready capacity tables
- standardization of pipeline and key-point identifiers
- cleaning / normalizing variance reasons

### Production Data

The production transform currently manipulates:

- monthly date
- selected Alberta and Saskatchewan production categories
- unit conversion to barrels/day
- a derived constraint classification

### Rail Data

The rail transform currently manipulates:

- year
- month
- rail volume in cubic meters
- derived date
- derived barrels/day value

But that rail path is not fully landed yet because the final output file is not present, and the script currently drops the derived barrels/day field before writing.

## Verification: `pipeline_capacity.csv` / `pipeline_flow.csv` Preview Line Splitting

Initial concern:

- The final pipeline outputs look broken when opened in plain-text preview because some rows appear to split across lines.

Verification result:

- This is not a row-structure bug in the CSV itself.
- Both files parse cleanly with a real CSV parser.
- Every data row matches the header width in both outputs.

What is happening:

- `pipeline_capacity.csv` has 883 physical text lines but 655 CSV records including the header.
- `pipeline_flow.csv` has 5,498 physical text lines but 4,008 CSV records including the header.
- The extra physical lines come from embedded `CRLF` characters inside quoted text cells.

Where the embedded line breaks are:

- In both outputs, the affected field is `pipeline_original`.
- `pipeline_capacity.csv` has 228 data rows with embedded `CRLF` in `pipeline_original`.
- `pipeline_flow.csv` has 1,490 data rows with embedded `CRLF` in `pipeline_original`.

Source of the issue:

- The raw Enbridge source already contains the pipeline value as `Enbridge Canadian Mainline system\r\n`.
- The transform preserves that original value into `pipeline_original`.
- CSV-aware tools keep the row intact because the value is quoted.
- Plain-text previewers make it look like the row is broken because they render the embedded newline literally.

Conclusion:

- Excel behavior is consistent with a proper CSV reader.
- Plain-text preview behavior is misleading but understandable.
- So this is not a CSV corruption issue.
- It is still a data-hygiene issue worth fixing by stripping `\r` / `\n` from preserved original text columns before writing.

## Important Mismatches and Gaps

### 1. Local outputs and current code are not perfectly aligned

The clearest example is the production transform:

- The current script logic uses lowercase / underscore style category values such as `constrained` and `semi_constrained`.
- The current local `western_canada_estimated_production.csv` contains title-cased / hyphenated values such as `Constrained` and `Semi-Constrained`.

That strongly suggests at least some local outputs were generated from an earlier version of the code or manually adjusted outside the tracked source.

### 2. Pipeline text normalization is incomplete

The final standardized pipeline outputs still preserve embedded line breaks in `pipeline_original`.

Also, `capacity_basis_standard` is not fully standardized into a consistent slug form. Current observed values include:

- `ex-gretna`
- `haskett_border`
- `burnaby, sumas, westridge`

So the "standard" field is not fully standardized yet.

### 3. Tableau is still pointed at older production files

The Tableau workbook at `Tableau/Alberta Oil Production.twb` references:

- `AB_SK_production.csv`
- `AB_SK_cubic_meters_per_day.csv`

It does not reference:

- `western_canada_estimated_production.csv`
- `pipeline_flow.csv`
- `pipeline_capacity.csv`
- `monthly_rail_exports.csv`

That means the current workbook is stale relative to the current transform outputs and does not appear to be wired into the newer pipeline work.

### 4. Rail is only partially integrated

- Rail raw data exists locally.
- The rail transform script exists.
- The expected final rail CSV is missing.
- Tableau does not appear to reference rail output yet.

### 5. No orchestrator exists in the current tree

There are `main()` functions on the individual scripts, but no single entry point for:

- extract only
- transform only
- full refresh
- validation / post-run checks

There is a commit message from May 4, 2026 mentioning an orchestrator, but in the current tree that seems to have been more of a utility abstraction step than a real project-level runner.

### 6. The load / database path is unfinished

- `pipeline/load/` is empty
- there is no schema or load implementation in the project directory
- there is no migration folder present here

### 7. `docker-compose.yml` looks unfinished

Current issues visible in the file:

- duplicate `container_name` value for both services
- likely env-var typos: `POSGRES_DB`, `POSGRES_PORT`, `POSTGREST_PASSWORD`
- Flyway points to `./db/migrations`, but no `db/` folder is present in this project directory

So the database side looks like an early stub, not a working deployment path.

### 8. Minor naming roughness

- `enbrdige_mainline_capacity.csv` is misspelled in the stage-1 output/config naming

Not critical, but worth cleaning up before formalizing the project structure.

## What Likely Runs Today

Based on code inspection and the local environment, the current project likely runs as a manual script chain, not as a cohesive pipeline product.

Probable manual execution order:

1. `pipeline/extract/cer_extract.py`
2. `pipeline/transform/a_1_em_pipeline_transform.py`
3. `pipeline/transform/a_1_ks_pipeline_transform.py`
4. `pipeline/transform/a_1_tm_pipeline_transform.py`
5. `pipeline/transform/a_2_throughput_standardization.py`
6. `pipeline/transform/b_1_production_transform.py`
7. `pipeline/transform/c_1_rail_transform.py`

Important caveat:

- I validated the current source files by compiling them, but I did not re-run the full pipeline from scratch because that would overwrite the current local outputs.

## What The Project Appears To Be Trying To Become

The shape of the project suggests this intended direction:

- pull public CER and related throughput / production / rail source files
- normalize them into analysis-ready CSV tables
- load them into either Tableau directly or eventually into Postgres
- analyze Alberta / Western Canada production against transportation constraints
- especially pipeline capacity, utilization, and possible rail substitution

That direction is coherent. The missing pieces are mainly orchestration, reproducibility, integration, and documentation.

## Next Steps I Would Take

### Immediate documentation next step

Use this journal as the source material for a proper README that explains:

- project goal
- data sources
- run order
- outputs
- known limitations

### Engineering next steps

1. Build a real orchestrator / CLI entry point.
   - One command should run extract + transform end to end.
   - Separate subcommands should exist for extract, pipeline transforms, production transform, rail transform, and validation.

2. Add a post-run validation step.
   - Check that expected output files exist.
   - Check row counts and date ranges.
   - Check for embedded newlines in preserved text fields.

3. Clean the text fields before output.
   - Strip `\r` and `\n` from `pipeline_original`, `key_point_original`, and related preserved columns.
   - Make `capacity_basis_standard` use the same slugging rules as `key_point_standard`.

4. Reconcile code vs artifact drift.
   - Re-run outputs from current code in a controlled way.
   - Confirm whether the current local CSVs are still the desired truth.

5. Finish the rail path.
   - Decide the final schema for rail output.
   - Keep the derived barrels/day field if it is analytically useful.
   - Produce the final rail CSV and wire it into downstream use.

6. Decide whether Tableau remains the primary consumer or whether Postgres becomes real.
   - If Tableau-first, reconnect the workbook to the current transformed files.
   - If database-first, finish schema, migrations, load logic, and documentation.

7. Add minimal project packaging and reproducibility.
   - dependency manifest
   - run instructions
   - environment assumptions

## Summary

As of August 26, 2026, the project has a real extraction layer and a meaningful transform layer, especially for pipeline throughput. The core analytical idea is clear and most of the heavy lifting for the CER data model is already in place.

What is missing is not the concept. What is missing is the operational layer:

- one command to run it
- one place to document it
- one set of validated outputs
- one integrated downstream consumer

That is the likely bridge from "good exploratory pipeline work" to "project I can confidently pick up again."
