"""Validate CER pipeline-throughput CSVs and materialize accepted rows.

Run all configured sources with ``python -m pipeline.validate.a_0_pipeline_validation``.
The validator preserves downloaded raw files, writes accepted rows to
``data/validated``, sends rejected rows to ``data/quarantine``, and records a
JSON report plus row-count history under ``data/validation``.
"""

from __future__ import annotations

import argparse
import csv
import math
import re
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterable

from pipeline.config.settings import (
    QUARANTINE_BUCKET,
    RAW_BUCKET,
    VALIDATED_RAW_BUCKET,
    VALIDATION_REPORTS_BUCKET,
)
from pipeline.config.sources import CER_PIPELINE_SOURCES
from pipeline.validate.contracts import (
    ALLOWED_DIRECTIONS,
    ALLOWED_PRODUCTS,
    ALLOWED_TRADE_TYPES,
    CONTRACTS,
    ThroughputContract,
)
from pipeline.validate.common import prior_row_count, print_validation_result, write_report
from pipeline.validate.models import Severity, ValidationIssue, ValidationResult


def normalized_text(value: str | None) -> str:
    """Normalize line breaks and whitespace before text comparison."""
    return re.sub(r"\s+", " ", value or "").strip()


def is_blank(value: str | None) -> bool:
    return not normalized_text(value)


def as_number(value: str | None) -> float | None:
    if is_blank(value):
        return None
    try:
        parsed = float(str(value))
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def is_helper_row(source_name: str, row: dict[str, str]) -> bool:
    if source_name == "transmountain":
        return normalized_text(row.get("Key Point")) == "system"
    return is_blank(row.get("Product")) or normalized_text(row.get("Product")) == "total"


def issue(
    issues_by_row: dict[int, list[ValidationIssue]],
    row_number: int,
    rule: str,
    message: str,
) -> None:
    issues_by_row[row_number].append(
        ValidationIssue(rule=rule, message=message, severity=Severity.ERROR, row_number=row_number)
    )


def validate_date_fields(row: dict[str, str], row_number: int, issues_by_row: dict[int, list[ValidationIssue]]) -> None:
    try:
        parsed = datetime.strptime(row.get("Date", ""), "%Y-%m-%d").date()
    except ValueError:
        issue(issues_by_row, row_number, "date_format", "Date must use YYYY-MM-DD.")
        return
    if parsed.day != 1:
        issue(issues_by_row, row_number, "month_start", "Date must be the first day of a month.")
    if parsed > date.today():
        issue(issues_by_row, row_number, "future_date", "Date cannot be in the future.")
    try:
        month = int(row.get("Month", ""))
        year = int(row.get("Year", ""))
    except ValueError:
        issue(issues_by_row, row_number, "month_year_type", "Month and Year must be integers.")
        return
    if not 1 <= month <= 12 or year < 1000 or year > 9999:
        issue(issues_by_row, row_number, "month_year_range", "Month or Year is outside its permitted range.")
    elif (month, year) != (parsed.month, parsed.year):
        issue(issues_by_row, row_number, "month_year_match", "Month and Year must agree with Date.")


def validate_product_row(
    row: dict[str, str], row_number: int, issues_by_row: dict[int, list[ValidationIssue]]
) -> None:
    for column, lower, upper in (("Latitude", 0.0, 90.0), ("Longitude", -180.0, 0.0)):
        number = as_number(row.get(column))
        if number is None or not lower <= number <= upper:
            issue(issues_by_row, row_number, column.lower().replace(" ", "_"), f"{column} is required and out of range.")
    if normalized_text(row.get("Direction Of Flow")) not in ALLOWED_DIRECTIONS:
        issue(issues_by_row, row_number, "direction_of_flow", "Direction Of Flow must be cardinal.")
    if normalized_text(row.get("Trade Type")) not in ALLOWED_TRADE_TYPES:
        issue(issues_by_row, row_number, "trade_type", "Trade Type is not allowed.")
    throughput = as_number(row.get("Throughput (1000 m3/d)"))
    if throughput is None or throughput < 0:
        issue(issues_by_row, row_number, "throughput", "Throughput must be finite and non-negative.")

    for column in ("Committed Volumes (1000 m3/d)", "Uncommitted Volumes (1000 m3/d)"):
        if column in row and not is_blank(row[column]):
            number = as_number(row[column])
            if number is None or number < 0:
                issue(issues_by_row, row_number, "volume_metric", f"{column} must be finite and non-negative.")
    for column in ("Nameplate Capacity (1000 m3/d)", "Available Capacity (1000 m3/d)"):
        if not is_blank(row.get(column)):
            number = as_number(row.get(column))
            if number is None or number <= 0:
                issue(issues_by_row, row_number, "capacity_metric", f"{column} must be finite and positive.")
    if row.get("Reason For Variance") not in (None, "") and is_blank(row.get("Reason For Variance")):
        issue(issues_by_row, row_number, "reason_for_variance", "Reason For Variance cannot be whitespace only.")


def validate_row(
    contract: ThroughputContract, row: dict[str, str], row_number: int, issues_by_row: dict[int, list[ValidationIssue]]
) -> None:
    validate_date_fields(row, row_number, issues_by_row)
    if normalized_text(row.get("Company")) != contract.company:
        issue(issues_by_row, row_number, "company", "Company does not match the source contract.")
    if normalized_text(row.get("Pipeline")) != contract.pipeline:
        issue(issues_by_row, row_number, "pipeline", "Pipeline does not match the source contract.")

    key_point = normalized_text(row.get("Key Point"))
    if contract.source_name == "enbridge_mainline":
        if not key_point or not re.search(r"[A-Za-z0-9]", key_point):
            issue(issues_by_row, row_number, "key_point", "Key Point must contain an alphanumeric character.")
    elif key_point not in (contract.key_points or frozenset()):
        issue(issues_by_row, row_number, "key_point", "Key Point is not allowed for this source.")

    product = normalized_text(row.get("Product"))
    if product and product not in ALLOWED_PRODUCTS:
        issue(issues_by_row, row_number, "product", "Product is not in the shared allowed domain.")
    helper = is_helper_row(contract.source_name, row)
    if contract.source_name == "transmountain":
        if not helper and (not product or product == "total"):
            issue(issues_by_row, row_number, "product_helper", "Blank or total Product is allowed only on a system helper row.")
    elif not helper:
        if not product or product == "total":
            issue(issues_by_row, row_number, "product_helper", "Blank or total Product is allowed only on a helper row.")

    if not helper:
        validate_product_row(row, row_number, issues_by_row)
        if contract.source_name == "keystone":
            available = as_number(row.get("Available Capacity (1000 m3/d)"))
            if available is None or available <= 0:
                issue(issues_by_row, row_number, "available_capacity", "Keystone product rows require positive available capacity.")


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)
        return reader.fieldnames or [], list(reader)


def write_rows(path: Path, headers: list[str], rows: Iterable[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def validate_file(
    contract: ThroughputContract,
    raw_path: Path,
    validated_dir: Path,
    quarantine_dir: Path,
    reports_dir: Path,
) -> ValidationResult:
    now = datetime.now(timezone.utc)
    timestamp = now.strftime("%Y%m%dT%H%M%SZ")
    issues: list[ValidationIssue] = []
    if not raw_path.exists():
        result = ValidationResult(contract.source_name, raw_path.name, now, 0, 0, 0, [
            ValidationIssue("file_missing", "Raw input file is missing.", Severity.ERROR)
        ])
        write_report(result, reports_dir, timestamp)
        return result
    try:
        headers, rows = read_csv(raw_path)
    except (OSError, UnicodeDecodeError, csv.Error) as error:
        result = ValidationResult(contract.source_name, raw_path.name, now, 0, 0, 0, [
            ValidationIssue("file_unreadable", str(error), Severity.ERROR)
        ])
        write_report(result, reports_dir, timestamp)
        return result

    duplicates = [header for header, count in Counter(headers).items() if count > 1]
    missing = [header for header in contract.required_columns if header not in headers]
    if duplicates:
        issues.append(ValidationIssue("duplicate_headers", f"Duplicate headers: {', '.join(duplicates)}.", Severity.ERROR))
    if missing:
        issues.append(ValidationIssue("missing_headers", f"Missing headers: {', '.join(missing)}.", Severity.ERROR))
    if not rows:
        issues.append(ValidationIssue("empty_file", "Input file has no data rows.", Severity.ERROR))
    if issues:
        result = ValidationResult(contract.source_name, raw_path.name, now, len(rows), 0, 0, issues)
        write_report(result, reports_dir, timestamp)
        return result

    issues_by_row: dict[int, list[ValidationIssue]] = defaultdict(list)
    for row_number, row in enumerate(rows, start=2):
        validate_row(contract, row, row_number, issues_by_row)

    normalized_keys: dict[tuple[str, ...], list[int]] = defaultdict(list)
    for row_number, row in enumerate(rows, start=2):
        key = tuple(normalized_text(row.get(column)) for column in contract.unique_key)
        normalized_keys[key].append(row_number)
    for row_numbers in normalized_keys.values():
        if len(row_numbers) > 1:
            for row_number in row_numbers:
                issue(issues_by_row, row_number, "duplicate_key", "Normalized unique key is duplicated.")

    invalid_row_numbers = set(issues_by_row)
    accepted = [row for row_number, row in enumerate(rows, start=2) if row_number not in invalid_row_numbers]
    rejected = [row for row_number, row in enumerate(rows, start=2) if row_number in invalid_row_numbers]
    issues.extend(issue for row_issues in issues_by_row.values() for issue in row_issues)

    history_path = reports_dir / "row_count_history.jsonl"
    previous_count = prior_row_count(history_path, contract.source_name)
    if previous_count is not None and len(rows) < previous_count:
        issues.append(
            ValidationIssue(
                "row_count_decrease",
                f"Row count decreased from {previous_count} to {len(rows)}.",
                Severity.WARNING,
            )
        )

    accepted_path = validated_dir / raw_path.name
    write_rows(accepted_path, headers, accepted)
    quarantine_path: Path | None = None
    if rejected:
        quarantine_path = quarantine_dir / contract.source_name / f"{raw_path.stem}-{timestamp}.csv"
        write_rows(quarantine_path, headers, rejected)
    result = ValidationResult(
        source_name=contract.source_name,
        raw_filename=raw_path.name,
        retrieved_at=now,
        total_rows=len(rows),
        passed_rows=len(accepted),
        rejected_rows=len(rejected),
        issues=issues,
        accepted_path=str(accepted_path),
        quarantine_path=str(quarantine_path) if quarantine_path else None,
    )
    write_report(result, reports_dir, timestamp)
    return result


def validate_pipeline_throughput(
    raw_dir: Path = RAW_BUCKET,
    validated_dir: Path = VALIDATED_RAW_BUCKET,
    quarantine_dir: Path = QUARANTINE_BUCKET,
    reports_dir: Path = VALIDATION_REPORTS_BUCKET,
) -> list[ValidationResult]:
    """Validate every configured pipeline source and return all results."""
    results: list[ValidationResult] = []
    for source in CER_PIPELINE_SOURCES:
        source_name = str(source["name"])
        contract = CONTRACTS[source_name]
        result = validate_file(
            contract,
            raw_dir / str(source["raw_filename"]),
            validated_dir,
            quarantine_dir,
            reports_dir,
        )
        results.append(result)
    fatal_sources = [result.source_name for result in results if result.fatal]
    if fatal_sources:
        raise RuntimeError("Pipeline input validation failed for: " + ", ".join(fatal_sources))
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, default=RAW_BUCKET)
    parser.add_argument("--validated-dir", type=Path, default=VALIDATED_RAW_BUCKET)
    parser.add_argument("--quarantine-dir", type=Path, default=QUARANTINE_BUCKET)
    parser.add_argument("--reports-dir", type=Path, default=VALIDATION_REPORTS_BUCKET)
    args = parser.parse_args()
    for result in validate_pipeline_throughput(
        args.raw_dir, args.validated_dir, args.quarantine_dir, args.reports_dir
    ):
        print_validation_result(result)


if __name__ == "__main__":
    main()
