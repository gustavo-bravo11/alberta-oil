"""Validate production and rail workbooks into accepted CSV inputs."""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

import polars as pl

from pipeline.config.settings import QUARANTINE_BUCKET, RAW_BUCKET, VALIDATED_RAW_BUCKET, VALIDATION_REPORTS_BUCKET
from pipeline.config.sources import CER_PRODUCTION, CER_RAIL_EXPORTS
from pipeline.transform.c_1_rail_transform import MONTH_NUM, clean_column_names, read_rail_sheet, source_update_metadata
from pipeline.validate.models import Severity, ValidationIssue, ValidationResult
from pipeline.validate.raw_throughput import prior_row_count, write_report
from pipeline.utils.workbook_metadata import production_report_metadata


PRODUCTION_COLUMNS = (
    "month", "nl_light", "nl_heavy", "on", "nb", "mb", "nwt", "sk_light", "sk_heavy",
    "ab_conv_light", "ab_conv_heavy", "ab_upgraded", "ab_non_upgraded", "bc_light", "bc_cond",
    "ab_cond", "ns_cond", "sk_cond", "canada_total", "raw_mined_bitumen", "raw_in_situ_bitumen",
)
PRODUCTION_COMPONENTS = tuple(column for column in PRODUCTION_COLUMNS if column not in {
    "month", "canada_total", "raw_mined_bitumen", "raw_in_situ_bitumen",
})


def normalize_header(value: str) -> str:
    return value.strip().lower().replace(" ", "_").replace("-", "_")


def finite_nonnegative(value: object) -> bool:
    return isinstance(value, (int, float)) and math.isfinite(float(value)) and float(value) >= 0


def write_frames(accepted: pl.DataFrame, rejected: pl.DataFrame, source_name: str, filename: str, timestamp: str) -> tuple[str, str | None]:
    accepted_path = VALIDATED_RAW_BUCKET / filename
    accepted_path.parent.mkdir(parents=True, exist_ok=True)
    accepted.write_csv(accepted_path)
    quarantine_path: Path | None = None
    if rejected.height:
        quarantine_path = QUARANTINE_BUCKET / source_name / f"{Path(filename).stem}-{timestamp}.csv"
        quarantine_path.parent.mkdir(parents=True, exist_ok=True)
        rejected.write_csv(quarantine_path)
    return str(accepted_path), str(quarantine_path) if quarantine_path else None


def finalize(
    source_name: str, raw_filename: str, rows: pl.DataFrame, invalid: set[int], issues: list[ValidationIssue], accepted_filename: str
) -> ValidationResult:
    now = datetime.now(timezone.utc)
    timestamp = now.strftime("%Y%m%dT%H%M%SZ")
    accepted = rows.filter([index not in invalid for index in range(rows.height)])
    rejected = rows.filter([index in invalid for index in range(rows.height)])
    history = VALIDATION_REPORTS_BUCKET / "row_count_history.jsonl"
    previous = prior_row_count(history, source_name)
    if previous is not None and rows.height < previous:
        issues.append(ValidationIssue("row_count_decrease", f"Row count decreased from {previous} to {rows.height}.", Severity.WARNING))
    accepted_path, quarantine_path = write_frames(accepted, rejected, source_name, accepted_filename, timestamp)
    result = ValidationResult(source_name, raw_filename, now, rows.height, accepted.height, rejected.height, issues, accepted_path, quarantine_path)
    write_report(result, VALIDATION_REPORTS_BUCKET, timestamp)
    return result


def validate_production() -> ValidationResult:
    raw_path = RAW_BUCKET / str(CER_PRODUCTION["raw_filename"])
    frame = pl.read_excel(raw_path, sheet_name=str(CER_PRODUCTION["sheet_name"]), engine="xlsx2csv", drop_empty_cols=True, infer_schema_length=10000)
    frame = frame.rename(normalize_header)
    missing = [column for column in PRODUCTION_COLUMNS if column not in frame.columns]
    now = datetime.now(timezone.utc)
    if missing:
        result = ValidationResult("cer_production", raw_path.name, now, frame.height, 0, 0, [ValidationIssue("missing_headers", f"Missing headers: {', '.join(missing)}.", Severity.ERROR)])
        write_report(result, VALIDATION_REPORTS_BUCKET, now.strftime("%Y%m%dT%H%M%SZ"))
        return result
    frame = frame.select(PRODUCTION_COLUMNS).filter(
        pl.any_horizontal([pl.col(column).is_not_null() for column in PRODUCTION_COLUMNS[1:]])
    ).with_row_index("_row")
    invalid: set[int] = set()
    issues: list[ValidationIssue] = []
    seen_months: set[date] = set()
    for row in frame.to_dicts():
        row_index = int(row["_row"])
        try:
            month = datetime.strptime(str(row["month"]), "%b-%y").date()
            if month > date.today() or month in seen_months:
                raise ValueError
            seen_months.add(month)
        except ValueError:
            invalid.add(row_index); issues.append(ValidationIssue("month", "Month is invalid, future, or duplicated.", Severity.ERROR, row_index + 2)); continue
        for column in PRODUCTION_COLUMNS[1:]:
            value = row[column]
            if value is not None and not finite_nonnegative(value):
                invalid.add(row_index); issues.append(ValidationIssue("production_metric", f"{column} must be finite and non-negative.", Severity.ERROR, row_index + 2))
        if row["canada_total"] is None:
            invalid.add(row_index); issues.append(ValidationIssue("canada_total", "Canada Total is required.", Severity.ERROR, row_index + 2))
        if row["canada_total"] is not None:
            component_sum = sum(float(row[column] or 0) for column in PRODUCTION_COMPONENTS)
            if abs(component_sum - float(row["canada_total"])) > 1e-6:
                issues.append(ValidationIssue("canada_total_reconciliation", f"Reported total differs from components by {component_sum - float(row['canada_total']):.6f}.", Severity.WARNING, row_index + 2))
    report = production_report_metadata(raw_path)
    if datetime.fromisoformat(report["report_date"]).date() < date.fromisoformat(report["latest_data_month"]):
        issues.append(ValidationIssue("report_date", "Report date precedes latest data month.", Severity.ERROR))
    return finalize("cer_production", raw_path.name, frame.drop("_row"), invalid, issues, "cer_production_validated.csv")


def validate_rail() -> ValidationResult:
    raw_path = RAW_BUCKET / str(CER_RAIL_EXPORTS["raw_filename"])
    frame = read_rail_sheet(raw_path, header_row=7, use_columns="B:G").rename(clean_column_names).with_row_index("_row")
    required = {"year", "month", "volume_m3_per_day"}
    now = datetime.now(timezone.utc)
    if not required.issubset(frame.columns):
        missing = sorted(required - set(frame.columns))
        result = ValidationResult("cer_rail", raw_path.name, now, frame.height, 0, 0, [ValidationIssue("missing_headers", f"Missing headers: {', '.join(missing)}.", Severity.ERROR)])
        write_report(result, VALIDATION_REPORTS_BUCKET, now.strftime("%Y%m%dT%H%M%SZ"))
        return result
    # Footnotes and unit legends share the selected worksheet range but have no volume.
    frame = frame.filter(pl.col("volume_m3_per_day").is_not_null()).with_columns(pl.col("year").forward_fill())
    invalid: set[int] = set(); issues: list[ValidationIssue] = []; seen: set[tuple[int, int]] = set(); latest: date | None = None
    for row in frame.to_dicts():
        row_index = int(row["_row"]); month_name = str(row["month"] or "").strip().lower()
        if month_name not in MONTH_NUM:
            if any(value is not None for key, value in row.items() if key != "_row"):
                invalid.add(row_index); issues.append(ValidationIssue("month", "Month must be a full month name.", Severity.ERROR, row_index + 9))
            continue
        try:
            year = int(row["year"])
            month = date(year, MONTH_NUM[month_name], 1)
            if (year, month.month) in seen:
                raise ValueError
            seen.add((year, month.month)); latest = max(latest, month) if latest else month
        except (TypeError, ValueError):
            invalid.add(row_index); issues.append(ValidationIssue("year_month", "Year is invalid or duplicated.", Severity.ERROR, row_index + 9)); continue
        if not finite_nonnegative(row["volume_m3_per_day"]):
            invalid.add(row_index); issues.append(ValidationIssue("volume_m3_per_day", "Volume must be finite and non-negative.", Severity.ERROR, row_index + 9))
    metadata = source_update_metadata(raw_path)
    if latest is None or date.fromisoformat(metadata["report_date"][:10]) < latest:
        issues.append(ValidationIssue("report_date", "Report date precedes latest rail month.", Severity.ERROR))
    return finalize("cer_rail", raw_path.name, frame.drop("_row"), invalid, issues, "cer_rail_validated.csv")


def validate_workbook_inputs() -> list[ValidationResult]:
    results = [validate_production(), validate_rail()]
    for result in results:
        print(f"{result.source_name}: received={result.total_rows}, passed={result.passed_rows}, rejected={result.rejected_rows}, fatal={result.fatal}")
    fatal = [result.source_name for result in results if result.fatal]
    if fatal:
        raise RuntimeError("Workbook input validation failed for: " + ", ".join(fatal))
    return results


if __name__ == "__main__":
    validate_workbook_inputs()
