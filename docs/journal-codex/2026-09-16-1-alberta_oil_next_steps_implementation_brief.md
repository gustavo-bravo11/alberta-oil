# Alberta Oil Pipeline — Next Steps Implementation Brief

**STATUS: COMPLETED**

## Purpose

This document consolidates the implementation work discussed after reviewing:

- the current orchestrator,
- the validation layer,
- the existing test structure,
- the latest validation/lineage journal,
- and the gaps between what is already implemented and what is still untested or not fully wired into the DAG.

The goal is to give Codex a concrete implementation brief without introducing new architectural decisions beyond what has already been agreed.

---

# 1. Expand test coverage beyond `test_raw_throughput.py`

## Current situation

The `project/tests/` folder currently contains only:

```text
test_raw_throughput.py
```

However, the project already has validation logic for additional source types, including:

- pipeline throughput,
- workbook inputs,
- report dates,
- production data,
- rail data.

The validation logic exists, but most of it is not covered by automated tests.

## Required change

Add tests for the validators that already exist.

At minimum, add:

```text
test_workbook_inputs.py
test_report_dates.py
```

If production- or rail-specific helpers are sufficiently separate, those can either be tested in these files or split into more targeted files.

The goal is for test coverage to reflect the actual validation path of the pipeline.

---

# 2. Fix temporary test directory creation

## Current issue

`test_raw_throughput.py` creates temporary directories inside the repository's test directory by using `TemporaryDirectory(..., dir=Path(__file__).parent)` or equivalent logic.

This can leave `tmp...` folders inside `project/tests/` when:

- a test run is interrupted,
- a process is killed,
- Windows temporarily holds a file handle,
- or cleanup does not complete normally.

These folders are test artifacts and should not be created inside the repository.

## Required change

Use the system temporary directory instead.

Preferred approaches:

### Option A — pytest `tmp_path`

Use pytest's built-in fixture:

```python
def test_something(tmp_path):
    ...
```

This is preferred where practical.

### Option B — standard `TemporaryDirectory`

If retaining `TemporaryDirectory`, do not pass a repository directory:

```python
with TemporaryDirectory() as temp_dir:
    ...
```

Do not create temp folders inside `project/tests`.

Existing leftover temp folders can be deleted once no tests are running.

---

# 3. Add dynamic production-sheet fallback tests

## Context

The production workbook contains a sheet whose name changes with the reporting year.

The intended behavior is:

1. determine the current year,
2. first try the current-year production sheet,
3. if that sheet does not exist, fall back to the previous year's sheet,
4. stop there.

This should not become a broad search across many historical sheets.

## Required tests

At minimum:

### Case 1 — current year exists

Given a workbook containing the expected current-year sheet:

```text
current year → current-year sheet selected
```

### Case 2 — current year missing, previous year exists

Given a workbook where the current-year sheet is absent but the previous-year sheet exists:

```text
current year missing → previous-year sheet selected
```

### Case 3 — neither exists

Behavior should be deterministic and explicit.

Do not silently guess another sheet.

The existing production validator/extractor should either raise a clear error or return a clear validation failure depending on how the surrounding code is structured.

## Design constraint

Keep the fallback deliberately simple:

```text
current year
↓
previous year
↓
fail
```

Do not implement fuzzy sheet discovery unless there is a later requirement.

---

# 4. Add production reconciliation tests

## Context

Production validation includes internal reconciliation between reported components and an overall reported total.

The purpose is to identify inconsistencies in the source without modifying the source data.

## Required behavior

Where component values can be reconciled against a reported total:

```text
sum(component values) ≈ reported total
```

Use a reasonable tolerance if needed for source rounding.

## Required tests

### Case 1 — clean reconciliation

The components sum to the reported total.

Expected result:

```text
no reconciliation warning
```

### Case 2 — mismatch

The components do not reconcile to the reported total.

Expected result:

```text
warning raised / validation warning recorded
```

The validator should not:

- overwrite the reported total,
- silently alter component values,
- or invent a corrected value.

The purpose is observability, not correction.

---

# 5. Improve rail report-label date parsing

## Context

The rail workbook/report contains a human-readable label that includes a date.

A naive implementation that removes a fixed prefix or fixed text is fragile.

For example, code that assumes:

```text
"Numbers last updated on " + DATE
```

will fail unnecessarily if:

- whitespace changes,
- punctuation changes,
- capitalization changes,
- wording changes slightly,
- or someone edits the label manually.

## Required change

Parse the date by identifying a recognizable date pattern within the cell text rather than stripping an exact fixed prefix.

The logic should search for a date-like substring and then parse that substring.

Examples of acceptable source text variations might include:

```text
Numbers last updated on September 10, 2026
Numbers last updated: September 10, 2026
Last updated September 10th, 2026
Data current as of September 10, 2026
```

The implementation does not need to support every possible English sentence.

It should simply avoid depending on one exact prefix when the actual information needed is the date.

## Failure behavior

If no valid date can be identified:

- do not guess,
- do not substitute today's date,
- record a warning or validation failure according to the existing validator design.

## Required tests

Include at least:

- normal expected label,
- extra whitespace,
- minor punctuation variation,
- ordinal suffixes such as `10th`,
- no parseable date.

---

# 6. Wire `validate.report_dates` into the `validate` stage

## Current orchestrator behavior

The task registry includes:

```text
validate.pipeline_inputs
validate.report_dates
validate.workbook_inputs
```

However, the current `validate` target only includes:

```python
"validate": (
    "validate.pipeline_inputs",
    "validate.workbook_inputs",
)
```

This means `validate.report_dates` exists as a registered task but is not executed when the user runs:

```bash
python -m pipeline.orchestrator validate
```

## Required change

Update the validate target so that report-date validation is included.

For example:

```python
"validate": (
    "validate.pipeline_inputs",
    "validate.report_dates",
    "validate.workbook_inputs",
)
```

Check dependency ordering and avoid redundant execution.

The DAG resolver should continue handling shared dependencies automatically.

---

# 7. Add orchestrator tests

## Purpose

The custom orchestrator is now important enough to deserve direct unit tests.

Its behavior should not be validated only indirectly through manual runs.

## Areas to test

### Dependency resolution

Given a task with upstream dependencies, confirm:

- dependencies run before downstream tasks,
- each task is included only once,
- ordering is deterministic.

### Cycle detection

Create a small artificial cyclic task graph and confirm:

```text
cycle → ValueError
```

### Missing task detection

Attempt to resolve an unregistered task and confirm a clear error.

### `--no-deps` behavior

Confirm that dependency resolution can intentionally be disabled.

### Stage expansion

Confirm stage targets resolve to the intended granular tasks.

### Dry run

Where practical, verify that dry-run planning does not execute task runners.

The goal is to test the orchestration logic independently from CER network access.

---

# 8. Add retrieval-log tests for scheduled and forced runs

## Context

The orchestrator creates a `RunContext` with:

```text
run_id
run_type
```

The supported run types include at least:

```text
forced
scheduled
```

The extraction layer records retrieval metadata.

This is the basis for lineage and future scheduler integration.

## Required tests

Confirm that retrieval-log rows preserve:

```text
run_id
run_type
```

for both:

```text
forced
scheduled
```

At minimum test:

### Forced run

A manual/default invocation should write:

```text
run_type = forced
```

### Scheduled run

A scheduler-style invocation should write:

```text
run_type = scheduled
```

### Run ID

The same orchestrator invocation should retain the same `run_id` for all source retrievals produced during that run.

Different runs should receive different run IDs.

Where possible, mock actual network retrieval so these tests remain fast and deterministic.

---

# 9. Keep validation tests independent from live CER availability

Automated unit tests should not depend on the real CER website being available.

Use:

- small fixture CSVs,
- small synthetic workbooks,
- temporary files,
- mocks for HTTP retrieval where appropriate.

Live-source checks can later be implemented as integration tests, but they should not be required for the normal local test suite.

The normal test suite should be:

```text
fast
deterministic
offline
repeatable
```

---

# 10. Preserve warning vs fatal semantics

The validation layer already distinguishes different types of data-quality outcomes.

Tests should preserve that distinction.

Examples:

## Fatal

Cases such as:

- required source file missing,
- required columns missing,
- file unreadable,
- structurally unusable input.

These should stop the affected pipeline path.

## Warning

Cases such as:

- row count decreased from the previous run,
- reconciliation difference,
- potentially stale report-date metadata where the underlying data can still be inspected.

Warnings should remain observable but should not silently mutate source data.

Do not turn every warning into a fatal pipeline error unless explicitly required.

---

# 11. Do not redesign the pipeline while implementing these tests

This implementation pass should remain focused.

Do not:

- redesign the DuckDB schema,
- implement the load layer,
- introduce Airflow/Dagster/Prefect,
- change the pipeline/flow/capacity model again,
- or rewrite the orchestrator architecture.

Those are separate design tasks.

This work is specifically about:

```text
validation coverage
orchestrator coverage
lineage coverage
small validation robustness fixes
```

---

# 12. Verification after implementation

After the changes are complete, run the entire test suite.

Expected command will likely be:

```bash
pytest
```

or the project-equivalent invocation.

Report:

1. files added,
2. files modified,
3. number of tests passing,
4. any failing tests,
5. any warnings,
6. any behavior that required interpretation beyond this document.

Also run:

```bash
python -m pipeline.orchestrator list
```

and verify `validate.report_dates` appears in the intended stage.

A dry run should also be useful:

```bash
python -m pipeline.orchestrator validate --dry-run
```

Confirm the resolved execution plan contains the correct validation tasks and required upstream dependencies.

---

# 13. Later task — DAG visualization

This is **not part of the current implementation priority**, but preserve it as a later project-showcase enhancement.

Because the orchestrator already stores task dependencies in the `TASKS` registry, add a future utility that generates a DAG diagram automatically from that registry.

Graphviz would be a suitable lightweight option.

The important requirement is:

> Do not manually maintain a separate DAG diagram.

The diagram should be generated from the same dependency definitions that actually drive execution so the documentation cannot drift from the code.

A generated DAG image could later be embedded in the main project README to showcase the backend architecture.

---

# Completion criteria

This implementation pass is complete when:

- temporary test artifacts no longer appear inside the repository,
- production sheet fallback is tested,
- production reconciliation is tested,
- rail report-label date parsing is robust and tested,
- `validate.report_dates` is included in the orchestrator's validate stage,
- workbook/report-date validators have automated coverage,
- orchestrator dependency logic has automated coverage,
- forced/scheduled retrieval lineage has automated coverage,
- all tests pass locally,
- and no unrelated architecture redesign has been introduced.
