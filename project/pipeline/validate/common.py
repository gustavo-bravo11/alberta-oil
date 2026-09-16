"""Shared result, reporting, and accepted-row helpers for source validators."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import polars as pl

from pipeline.config.settings import QUARANTINE_BUCKET, VALIDATED_RAW_BUCKET, VALIDATION_REPORTS_BUCKET
from pipeline.validate.contracts import CONTRACT_VERSION
from pipeline.validate.models import Severity, ValidationIssue, ValidationResult


VALIDATOR_VERSION = "1.0.0"


def prior_row_count(history_path: Path, source_name: str) -> int | None:
    """Return the latest prior row count recorded for a source, if any."""
    if not history_path.exists():
        return None
    latest: int | None = None
    for line in history_path.read_text(encoding="utf-8").splitlines():
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if entry.get("source_name") == source_name:
            latest = int(entry["total_rows"])
    return latest


def write_report(result: ValidationResult, reports_dir: Path, timestamp: str) -> None:
    """Persist a validation result and append its row count to source history."""
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_path = reports_dir / f"{result.source_name}-{timestamp}.json"
    result.report_path = str(report_path)
    report = result.as_dict()
    report["contract_version"] = CONTRACT_VERSION
    report["validator_version"] = VALIDATOR_VERSION
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    history_path = reports_dir / "row_count_history.jsonl"
    with history_path.open("a", encoding="utf-8") as file:
        file.write(
            json.dumps(
                {
                    "source_name": result.source_name,
                    "raw_filename": result.raw_filename,
                    "retrieved_at": result.retrieved_at.isoformat(),
                    "total_rows": result.total_rows,
                }
            )
            + "\n"
        )


def finalize_frame(
    source_name: str,
    raw_filename: str,
    rows: pl.DataFrame,
    invalid: set[int],
    issues: list[ValidationIssue],
    accepted_filename: str,
) -> ValidationResult:
    """Write accepted/quarantined rows and return the source validation result."""
    now = datetime.now(timezone.utc)
    timestamp = now.strftime("%Y%m%dT%H%M%SZ")
    accepted = rows.filter([index not in invalid for index in range(rows.height)])
    rejected = rows.filter([index in invalid for index in range(rows.height)])
    history = VALIDATION_REPORTS_BUCKET / "row_count_history.jsonl"
    previous = prior_row_count(history, source_name)
    if previous is not None and rows.height < previous:
        issues.append(
            ValidationIssue(
                "row_count_decrease",
                f"Row count decreased from {previous} to {rows.height}.",
                Severity.WARNING,
            )
        )

    accepted_path = VALIDATED_RAW_BUCKET / accepted_filename
    accepted_path.parent.mkdir(parents=True, exist_ok=True)
    accepted.write_csv(accepted_path)
    quarantine_path: Path | None = None
    if rejected.height:
        quarantine_path = QUARANTINE_BUCKET / source_name / f"{Path(accepted_filename).stem}-{timestamp}.csv"
        quarantine_path.parent.mkdir(parents=True, exist_ok=True)
        rejected.write_csv(quarantine_path)

    result = ValidationResult(
        source_name,
        raw_filename,
        now,
        rows.height,
        accepted.height,
        rejected.height,
        issues,
        str(accepted_path),
        str(quarantine_path) if quarantine_path else None,
    )
    write_report(result, VALIDATION_REPORTS_BUCKET, timestamp)
    return result
