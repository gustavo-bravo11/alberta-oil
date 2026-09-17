"""Validate the CER production workbook into an accepted production CSV."""

from __future__ import annotations

import math
from datetime import date, datetime, timezone

import polars as pl

from pipeline.config.settings import (
    QUARANTINE_PRODUCTION_BUCKET,
    RAW_BUCKET,
    VALIDATED_PRODUCTION_BUCKET,
    VALIDATION_PRODUCTION_REPORTS_BUCKET,
)
from pipeline.config.sources import CER_PRODUCTION
from pipeline.utils.workbook_metadata import production_report_metadata
from pipeline.validate.common import finalize_frame, write_report
from pipeline.validate.models import Severity, ValidationIssue, ValidationResult


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


def validate_production() -> ValidationResult:
    """Validate historical production values and materialize accepted rows."""
    raw_path = RAW_BUCKET / str(CER_PRODUCTION["raw_filename"])
    frame = pl.read_excel(
        raw_path,
        sheet_name=str(CER_PRODUCTION["sheet_name"]),
        engine="xlsx2csv",
        drop_empty_cols=True,
        infer_schema_length=10000,
    ).rename(normalize_header)
    missing = [column for column in PRODUCTION_COLUMNS if column not in frame.columns]
    now = datetime.now(timezone.utc)
    if missing:
        result = ValidationResult(
            "cer_production", raw_path.name, now, frame.height, 0, 0,
            [ValidationIssue("missing_headers", f"Missing headers: {', '.join(missing)}.", Severity.ERROR)],
        )
        write_report(result, VALIDATION_PRODUCTION_REPORTS_BUCKET, now.strftime("%Y%m%dT%H%M%SZ"))
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
            invalid.add(row_index)
            issues.append(ValidationIssue("month", "Month is invalid, future, or duplicated.", Severity.ERROR, row_index + 2))
            continue
        for column in PRODUCTION_COLUMNS[1:]:
            value = row[column]
            if value is not None and not finite_nonnegative(value):
                invalid.add(row_index)
                issues.append(ValidationIssue("production_metric", f"{column} must be finite and non-negative.", Severity.ERROR, row_index + 2))
        if row["canada_total"] is None:
            invalid.add(row_index)
            issues.append(ValidationIssue("canada_total", "Canada Total is required.", Severity.ERROR, row_index + 2))
        else:
            component_sum = sum(float(row[column] or 0) for column in PRODUCTION_COMPONENTS)
            if abs(component_sum - float(row["canada_total"])) > 1e-6:
                issues.append(ValidationIssue("canada_total_reconciliation", f"Reported total differs from components by {component_sum - float(row['canada_total']):.6f}.", Severity.WARNING, row_index + 2))

    report = production_report_metadata(raw_path)
    if datetime.fromisoformat(report["report_date"]).date() < date.fromisoformat(report["latest_data_month"]):
        issues.append(ValidationIssue("report_date", "Report date precedes latest data month.", Severity.ERROR))
    return finalize_frame(
        "cer_production",
        raw_path.name,
        frame.drop("_row"),
        invalid,
        issues,
        "cer_production_validated.csv",
        validated_dir=VALIDATED_PRODUCTION_BUCKET,
        quarantine_dir=QUARANTINE_PRODUCTION_BUCKET,
        reports_dir=VALIDATION_PRODUCTION_REPORTS_BUCKET,
    )
