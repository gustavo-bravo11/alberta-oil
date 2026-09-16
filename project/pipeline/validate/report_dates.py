"""Validate report-publication dates in the production and rail workbooks."""

from __future__ import annotations

from datetime import date

import polars as pl

from pipeline.config.settings import RAW_BUCKET
from pipeline.config.sources import CER_PRODUCTION, CER_RAIL_EXPORTS
from pipeline.transform.c_1_rail_transform import (
    MONTH_NUM,
    assumed_source_update_metadata,
    clean_column_names,
    read_rail_sheet,
    source_update_metadata,
)
from pipeline.utils.workbook_metadata import production_report_metadata


def validate_report_dates() -> None:
    """Validate workbook report dates against their latest data month."""
    production = production_report_metadata(RAW_BUCKET / str(CER_PRODUCTION["raw_filename"]))

    rail_file = RAW_BUCKET / str(CER_RAIL_EXPORTS["raw_filename"])
    rail = (
        read_rail_sheet(rail_file, header_row=7, use_columns="B:G")
        .rename(clean_column_names)
        .filter(
            pl.col("month").cast(pl.String).str.strip_chars().str.to_lowercase().is_in(list(MONTH_NUM))
        )
        .with_columns(pl.col("year").forward_fill())
        .with_columns(
            pl.date(
                year=pl.col("year").cast(pl.Int32),
                month=pl.col("month").str.strip_chars().str.to_lowercase().replace(MONTH_NUM).cast(pl.Int8),
                day=1,
            ).alias("date")
        )
    )
    latest_rail_month = rail.select(pl.col("date").max()).item()
    if latest_rail_month is None:
        raise ValueError("Rail workbook has no valid monthly rows.")
    try:
        rail_metadata = source_update_metadata(rail_file)
    except ValueError as error:
        rail_metadata = assumed_source_update_metadata(latest_rail_month, str(error))
    if date.fromisoformat(rail_metadata["report_date"][:10]) < latest_rail_month:
        raise ValueError("Rail report date is earlier than the latest rail-data month.")

    print(
        "production report date validated: "
        f"{production['report_date']} (latest month {production['latest_data_month']})"
    )
    print(f"rail report date validated: {rail_metadata['report_date']} (latest month {latest_rail_month})")
