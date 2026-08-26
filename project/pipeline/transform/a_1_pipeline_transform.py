"""Create stage-1 pipeline flow and capacity files from CER throughput data.

Run every pipeline source:
    python -m pipeline.transform.a_1_pipeline_transform

Run one source:
    python -m pipeline.transform.a_1_pipeline_transform --pipeline keystone

The source-specific capacity rules remain explicit below.  The shared file
loading, header cleanup, unit conversion, text cleanup, and CSV writing live
in this module so they do not have to be maintained in three scripts.
"""

from __future__ import annotations

import argparse

import polars as pl

from pipeline.config.settings import CUBIC_M_TO_BARRELS, RAW_BUCKET, THROUGHPUT_STAGE_1
from pipeline.config.sources import CER_PIPELINE_SOURCES


COMMON_COLUMNS = [
    "date",
    "pipeline",
    "key_point",
    "latitude",
    "longitude",
    "direction_of_flow",
    "trade_type",
    "product",
    "throughput_1000_m3_d",
    "available_capacity_1000_m3_d",
]

FLOW_COLUMNS = [
    "date",
    "pipeline",
    "key_point",
    "latitude",
    "longitude",
    "direction_of_flow",
    "trade_type",
    "product",
    "throughput_m3_d",
    "throughput_barrels_d",
]

CAPACITY_COLUMNS = [
    "date",
    "pipeline",
    "capacity_basis",
    "total_throughput_m3_d",
    "total_throughput_barrels_d",
    "available_capacity_m3_d",
    "available_capacity_barrels_d",
    "reason_for_variance",
    "reported_available_capacity_utlization",
]


def normalize_column_name(column: str) -> str:
    """Convert a CER source header to the project's snake_case convention."""
    return (
        column.strip()
        .lower()
        .replace(" ", "_")
        .replace("-", "_")
        .replace("/", "_")
        .replace("(", "")
        .replace(")", "")
    )


def clean_text(column: str) -> pl.Expr:
    """Remove Excel line breaks and excess whitespace from a text column."""
    return (
        pl.col(column)
        .cast(pl.String)
        .str.replace_all(r"[\r\n]+", " ")
        .str.replace_all(r"\s{2,}", " ")
        .str.strip_chars()
    )


def base_frame(source: dict[str, object]) -> pl.LazyFrame:
    """Load and normalize the fields common to all three pipeline sources."""
    selected_columns = COMMON_COLUMNS.copy()
    if source["name"] != "enbridge_mainline":
        selected_columns.append("reason_for_variance")

    frame = (
        pl.scan_csv(RAW_BUCKET / str(source["raw_filename"]))
        .rename(normalize_column_name)
        .select(selected_columns)
        .with_columns(
            (pl.col("throughput_1000_m3_d") * 1000).alias("throughput_m3_d"),
            (pl.col("throughput_1000_m3_d") * CUBIC_M_TO_BARRELS * 1000).alias(
                "throughput_barrels_d"
            ),
            (pl.col("available_capacity_1000_m3_d") * 1000).alias(
                "available_capacity_m3_d"
            ),
            (pl.col("available_capacity_1000_m3_d") * CUBIC_M_TO_BARRELS * 1000).alias(
                "available_capacity_barrels_d"
            ),
            clean_text("pipeline").str.to_titlecase().alias("pipeline"),
            clean_text("key_point").alias("key_point"),
        )
        .drop(["throughput_1000_m3_d", "available_capacity_1000_m3_d"])
    )

    if source["name"] == "enbridge_mainline":
        return frame.with_columns(pl.lit(None, dtype=pl.String).alias("reason_for_variance"))

    return frame.with_columns(clean_text("reason_for_variance").alias("reason_for_variance"))


def write_flow(source: dict[str, object], frame: pl.LazyFrame) -> pl.LazyFrame:
    """Write the map-ready flow table and return the untrimmed flow rows."""
    if source["name"] == "enbridge_mainline":
        flow_rows = frame.filter(
            (pl.col("key_point") != "system")
            & pl.col("available_capacity_m3_d").is_not_null()
        )
    elif source["name"] == "keystone":
        flow_rows = frame.filter(pl.col("product") != "total")
    else:
        flow_rows = frame.filter(pl.col("key_point") != "system")

    flow_rows.select(FLOW_COLUMNS).sink_csv(THROUGHPUT_STAGE_1 / str(source["flow_locations_filename"]))
    print(f"Successfully transformed: {source['flow_locations_filename']}")
    return flow_rows


def capacity_by_key_point(source: dict[str, object], frame: pl.LazyFrame) -> pl.LazyFrame:
    """Build capacity where a key point carries the available-capacity value."""
    if source["name"] == "enbridge_mainline":
        rows = frame.filter(
            (pl.col("available_capacity_m3_d").is_not_null())
            & (pl.col("product") != "total")
            & pl.col("throughput_m3_d").is_not_null()
            & (pl.col("key_point") == "ex-Gretna")
        )
    else:
        rows = frame.filter(pl.col("product") != "total")

    return (
        rows.group_by(["date", "pipeline", "key_point"], maintain_order=True)
        .agg(
            pl.col("throughput_m3_d").sum().alias("total_throughput_m3_d"),
            pl.col("throughput_barrels_d").sum().alias("total_throughput_barrels_d"),
            pl.col("available_capacity_m3_d").first().alias("available_capacity_m3_d"),
            pl.col("available_capacity_barrels_d").first().alias("available_capacity_barrels_d"),
            pl.col("reason_for_variance").first().alias("reason_for_variance"),
        )
        .with_columns(
            (pl.col("total_throughput_m3_d") / pl.col("available_capacity_m3_d")).alias(
                "reported_available_capacity_utlization"
            )
        )
        .rename({"key_point": "capacity_basis"})
        .select(CAPACITY_COLUMNS)
    )


def transmountain_capacity(frame: pl.LazyFrame, flow_rows: pl.LazyFrame) -> pl.LazyFrame:
    """Join Trans Mountain's system capacity row to its non-system flow rows."""
    capacity_rows = frame.filter(pl.col("key_point") == "system").select(
        "date",
        "pipeline",
        "available_capacity_m3_d",
        "available_capacity_barrels_d",
        "reason_for_variance",
    )
    total_flow = flow_rows.group_by(["date", "pipeline"], maintain_order=True).agg(
        pl.col("throughput_m3_d").sum().alias("total_throughput_m3_d"),
        pl.col("throughput_barrels_d").sum().alias("total_throughput_barrels_d"),
        pl.col("key_point").unique().sort().str.join(", ").alias("capacity_basis"),
    )

    return (
        total_flow.join(capacity_rows, on=["date", "pipeline"], validate="1:1")
        .with_columns(
            (pl.col("total_throughput_m3_d") / pl.col("available_capacity_m3_d")).alias(
                "reported_available_capacity_utlization"
            )
        )
        .select(CAPACITY_COLUMNS)
    )


def transform_pipeline(source: dict[str, object]) -> None:
    """Create both stage-1 outputs for one named CER pipeline source."""
    frame = base_frame(source)
    flow_rows = write_flow(source, frame)
    capacity = (
        transmountain_capacity(frame, flow_rows)
        if source["name"] == "transmountain"
        else capacity_by_key_point(source, frame)
    )
    capacity.sink_csv(THROUGHPUT_STAGE_1 / str(source["capacity_filename"]))
    print(f"Successfully transformed: {source['capacity_filename']}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pipeline",
        choices=[str(source["name"]) for source in CER_PIPELINE_SOURCES],
        help="Transform only this pipeline; omit to transform all sources.",
    )
    args = parser.parse_args()

    THROUGHPUT_STAGE_1.mkdir(parents=True, exist_ok=True)
    for source in CER_PIPELINE_SOURCES:
        if args.pipeline is None or source["name"] == args.pipeline:
            transform_pipeline(source)


if __name__ == "__main__":
    main()
