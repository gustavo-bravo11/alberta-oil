"""Validate the CER rail workbook into an accepted rail CSV."""

from __future__ import annotations

import math
from datetime import date, datetime, timezone

import polars as pl

from pipeline.config.settings import RAW_BUCKET, VALIDATION_REPORTS_BUCKET
from pipeline.config.sources import CER_RAIL_EXPORTS
from pipeline.transform.c_1_rail_transform import MONTH_NUM, clean_column_names, read_rail_sheet, source_update_metadata
from pipeline.validate.common import finalize_frame, write_report
from pipeline.validate.models import Severity, ValidationIssue, ValidationResult


def finite_nonnegative(value: object) -> bool:
    return isinstance(value, (int, float)) and math.isfinite(float(value)) and float(value) >= 0


def validate_rail() -> ValidationResult:
    """Validate monthly rail volumes and materialize accepted rows."""
    raw_path = RAW_BUCKET / str(CER_RAIL_EXPORTS["raw_filename"])
    frame = read_rail_sheet(raw_path, header_row=7, use_columns="B:G").rename(clean_column_names).with_row_index("_row")
    required = {"year", "month", "volume_m3_per_day"}
    now = datetime.now(timezone.utc)
    if not required.issubset(frame.columns):
        missing = sorted(required - set(frame.columns))
        result = ValidationResult(
            "cer_rail", raw_path.name, now, frame.height, 0, 0,
            [ValidationIssue("missing_headers", f"Missing headers: {', '.join(missing)}.", Severity.ERROR)],
        )
        write_report(result, VALIDATION_REPORTS_BUCKET, now.strftime("%Y%m%dT%H%M%SZ"))
        return result

    frame = frame.filter(pl.col("volume_m3_per_day").is_not_null()).with_columns(pl.col("year").forward_fill())
    invalid: set[int] = set()
    issues: list[ValidationIssue] = []
    seen: set[tuple[int, int]] = set()
    latest: date | None = None
    for row in frame.to_dicts():
        row_index = int(row["_row"])
        month_name = str(row["month"] or "").strip().lower()
        if month_name not in MONTH_NUM:
            if any(value is not None for key, value in row.items() if key != "_row"):
                invalid.add(row_index)
                issues.append(ValidationIssue("month", "Month must be a full month name.", Severity.ERROR, row_index + 9))
            continue
        try:
            year = int(row["year"])
            month = date(year, MONTH_NUM[month_name], 1)
            if (year, month.month) in seen:
                raise ValueError
            seen.add((year, month.month))
            latest = max(latest, month) if latest else month
        except (TypeError, ValueError):
            invalid.add(row_index)
            issues.append(ValidationIssue("year_month", "Year is invalid or duplicated.", Severity.ERROR, row_index + 9))
            continue
        if not finite_nonnegative(row["volume_m3_per_day"]):
            invalid.add(row_index)
            issues.append(ValidationIssue("volume_m3_per_day", "Volume must be finite and non-negative.", Severity.ERROR, row_index + 9))

    metadata = source_update_metadata(raw_path)
    if latest is None or date.fromisoformat(metadata["report_date"][:10]) < latest:
        issues.append(ValidationIssue("report_date", "Report date precedes latest rail month.", Severity.ERROR))
    return finalize_frame("cer_rail", raw_path.name, frame.drop("_row"), invalid, issues, "cer_rail_validated.csv")
