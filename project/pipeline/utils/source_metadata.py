"""Append source-report metadata linked to the retrieval ledger."""

from __future__ import annotations

import csv
from pathlib import Path

from pipeline.config.settings import RAW_RETRIEVAL_LOG, TRANSFORMED_BUCKET


FIELDS = (
    "source_name", "raw_filename", "run_id", "run_type", "date_retrieved_utc",
    "report_date", "report_label", "report_sheet", "latest_data_month", "date_transformed",
)


def latest_retrieval(source_name: str, raw_filename: str) -> dict[str, str]:
    if not RAW_RETRIEVAL_LOG.exists():
        return {}
    with RAW_RETRIEVAL_LOG.open("r", newline="", encoding="utf-8") as file:
        rows = list(csv.DictReader(file))
    return next(
        (row for row in reversed(rows) if row.get("source_name") == source_name and row.get("raw_filename") == raw_filename),
        {},
    )


def append_source_metadata(source_name: str, raw_filename: str, metadata: dict[str, str], date_transformed: str) -> None:
    """Write one lineage row per transformed source refresh."""
    path = TRANSFORMED_BUCKET / "source_metadata.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    retrieval = latest_retrieval(source_name, raw_filename)
    write_header = not path.exists() or path.stat().st_size == 0
    row = {
        "source_name": source_name,
        "raw_filename": raw_filename,
        "run_id": retrieval.get("run_id", ""),
        "run_type": retrieval.get("run_type", ""),
        "date_retrieved_utc": retrieval.get("date_retrieved_utc", ""),
        "report_date": metadata["report_date"],
        "report_label": metadata["report_label"],
        "report_sheet": metadata.get("report_sheet", ""),
        "latest_data_month": metadata["latest_data_month"],
        "date_transformed": date_transformed,
    }
    with path.open("a", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS)
        if write_header:
            writer.writeheader()
        writer.writerow(row)
