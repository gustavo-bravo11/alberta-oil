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

from pipeline.config.settings import CUBIC_M_TO_BARRELS, THROUGHPUT_STAGE_1, VALIDATED_RAW_BUCKET
from pipeline.config.sources import CER_PIPELINE_SOURCES
from pipeline.utils.timestamps import current_utc_timestamp


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

RAW_VOLUME_COLUMNS = [
    "committed_volumes_1000_m3_d",
    "uncommitted_volumes_1000_m3_d",
]

COMMITTED_VOLUME_RECONCILIATION_TOLERANCE_M3_D = 1_000

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
    "capacity_scope",
    "total_throughput_m3_d",
    "total_throughput_barrels_d",
    "committed_volume_m3_d",
    "committed_volume_barrels_d",
    "uncommitted_volume_m3_d",
    "uncommitted_volume_barrels_d",
    "available_capacity_m3_d",
    "available_capacity_barrels_d",
    "reason_for_variance",
    "reported_available_capacity_utilization",
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
    raw_frame = pl.scan_csv(VALIDATED_RAW_BUCKET / str(source["raw_filename"])).rename(
        normalize_column_name
    )
    source_columns = raw_frame.collect_schema().names()
    selected_columns = COMMON_COLUMNS + [
        column for column in RAW_VOLUME_COLUMNS if column in source_columns
    ]
    if source["name"] != "enbridge_mainline":
        selected_columns.append("reason_for_variance")

    frame = (
        raw_frame.select(selected_columns)
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

    for volume in ("committed", "uncommitted"):
        raw_column = f"{volume}_volumes_1000_m3_d"
        if raw_column in source_columns:
            frame = frame.with_columns(
                (pl.col(raw_column).cast(pl.Float64, strict=False) * 1000).alias(
                    f"{volume}_volume_m3_d"
                ),
                (pl.col(raw_column).cast(pl.Float64, strict=False) * CUBIC_M_TO_BARRELS * 1000).alias(
                    f"{volume}_volume_barrels_d"
                ),
            ).drop(raw_column)
        else:
            frame = frame.with_columns(
                pl.lit(None, dtype=pl.Float64).alias(f"{volume}_volume_m3_d"),
                pl.lit(None, dtype=pl.Float64).alias(f"{volume}_volume_barrels_d"),
            )

    if source["name"] == "enbridge_mainline":
        return frame.with_columns(pl.lit(None, dtype=pl.String).alias("reason_for_variance"))

    return frame.with_columns(clean_text("reason_for_variance").alias("reason_for_variance"))


def write_flow(
    source: dict[str, object], frame: pl.LazyFrame, date_transformed: str
) -> pl.LazyFrame:
    """Write the map-ready flow table and return the untrimmed flow rows."""
    if source["name"] == "enbridge_mainline":
        flow_rows = frame.filter(
            (pl.col("key_point") != "system")
            & pl.col("throughput_m3_d").is_not_null()
        )
    elif source["name"] == "keystone":
        flow_rows = frame.filter(pl.col("product") != "total")
    else:
        flow_rows = frame.filter(pl.col("key_point") != "system")

    (
        flow_rows.select(FLOW_COLUMNS)
        .with_columns(pl.lit(date_transformed).alias("date_transformed"))
        .sink_csv(THROUGHPUT_STAGE_1 / str(source["flow_locations_filename"]))
    )
    print(f"Successfully transformed: {source['flow_locations_filename']}")
    return flow_rows


def nullable_sum(column: str) -> pl.Expr:
    """Sum a metric while retaining NULL when CER reported no component values."""
    return pl.when(pl.col(column).count() > 0).then(pl.col(column).sum()).otherwise(
        pl.lit(None, dtype=pl.Float64)
    ).alias(column)


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

    capacity = (
        rows.group_by(["date", "pipeline", "key_point"], maintain_order=True)
        .agg(
            pl.col("throughput_m3_d").sum().alias("total_throughput_m3_d"),
            pl.col("throughput_barrels_d").sum().alias("total_throughput_barrels_d"),
            nullable_sum("committed_volume_m3_d"),
            nullable_sum("committed_volume_barrels_d"),
            nullable_sum("uncommitted_volume_m3_d"),
            nullable_sum("uncommitted_volume_barrels_d"),
            pl.col("available_capacity_m3_d").first().alias("available_capacity_m3_d"),
            pl.col("available_capacity_barrels_d").first().alias("available_capacity_barrels_d"),
            pl.col("reason_for_variance").first().alias("reason_for_variance"),
        )
        .with_columns(
            (pl.col("total_throughput_m3_d") / pl.col("available_capacity_m3_d")).alias(
                "reported_available_capacity_utilization"
            ),
            pl.lit("key_point").alias("capacity_scope"),
        )
        .rename({"key_point": "capacity_basis"})
    )

    if source["name"] != "keystone":
        return capacity.select(CAPACITY_COLUMNS)

    # Keystone reports committed/uncommitted volumes on its Product=total
    # helper row, while total throughput remains the sum of product rows.
    component_rows = frame.filter(pl.col("product") == "total").select(
        "date",
        "pipeline",
        pl.col("key_point").alias("capacity_basis"),
        pl.col("committed_volume_m3_d").alias("reported_committed_volume_m3_d"),
        pl.col("committed_volume_barrels_d").alias("reported_committed_volume_barrels_d"),
        pl.col("uncommitted_volume_m3_d").alias("reported_uncommitted_volume_m3_d"),
        pl.col("uncommitted_volume_barrels_d").alias("reported_uncommitted_volume_barrels_d"),
    )
    return (
        capacity.join(
            component_rows,
            on=["date", "pipeline", "capacity_basis"],
            how="left",
            validate="1:1",
        )
        .with_columns(
            pl.col("reported_committed_volume_m3_d").alias("committed_volume_m3_d"),
            pl.col("reported_committed_volume_barrels_d").alias("committed_volume_barrels_d"),
            pl.col("reported_uncommitted_volume_m3_d").alias("uncommitted_volume_m3_d"),
            pl.col("reported_uncommitted_volume_barrels_d").alias(
                "uncommitted_volume_barrels_d"
            ),
        )
        .select(CAPACITY_COLUMNS)
    )


def transmountain_capacity(frame: pl.LazyFrame, flow_rows: pl.LazyFrame) -> pl.LazyFrame:
    """Join Trans Mountain's system capacity row to its non-system flow rows.

    Design choice: ``capacity_basis`` is ``system`` because CER reports the
    capacity and committed-volume breakdown at system scope. Total throughput
    remains the sum of the non-system key-point flow observations, rather than
    implying that the system capacity belongs to any individual key point.
    """
    capacity_rows = frame.filter(pl.col("key_point") == "system").select(
        "date",
        "pipeline",
        pl.lit("system").alias("capacity_basis"),
        pl.lit("system").alias("capacity_scope"),
        "committed_volume_m3_d",
        "committed_volume_barrels_d",
        "uncommitted_volume_m3_d",
        "uncommitted_volume_barrels_d",
        "available_capacity_m3_d",
        "available_capacity_barrels_d",
        "reason_for_variance",
    )
    total_flow = flow_rows.group_by(["date", "pipeline"], maintain_order=True).agg(
        pl.col("throughput_m3_d").sum().alias("total_throughput_m3_d"),
        pl.col("throughput_barrels_d").sum().alias("total_throughput_barrels_d"),
    )

    return (
        total_flow.join(capacity_rows, on=["date", "pipeline"], validate="1:1")
        .with_columns(
            (pl.col("total_throughput_m3_d") / pl.col("available_capacity_m3_d")).alias(
                "reported_available_capacity_utilization"
            )
        )
        .select(CAPACITY_COLUMNS)
    )


def reconciliation_exceptions(capacity: pl.LazyFrame) -> pl.DataFrame:
    """Return capacity rows where reported component volumes miss total throughput."""
    return (
        capacity.filter(
            pl.col("committed_volume_m3_d").is_not_null()
            & pl.col("uncommitted_volume_m3_d").is_not_null()
        )
        .with_columns(
            (
                (pl.col("committed_volume_m3_d") + pl.col("uncommitted_volume_m3_d"))
                - pl.col("total_throughput_m3_d")
            )
            .abs()
            .alias("reconciliation_difference_m3_d")
        )
        .filter(
            pl.col("reconciliation_difference_m3_d")
            > COMMITTED_VOLUME_RECONCILIATION_TOLERANCE_M3_D
        )
        .select(
            "date",
            "pipeline",
            "capacity_basis",
            "total_throughput_m3_d",
            "committed_volume_m3_d",
            "uncommitted_volume_m3_d",
            "reconciliation_difference_m3_d",
        )
        .collect()
    )


def transform_pipeline(source: dict[str, object]) -> None:
    """Create both stage-1 outputs for one named CER pipeline source."""
    date_transformed = current_utc_timestamp()
    frame = base_frame(source)
    flow_rows = write_flow(source, frame, date_transformed)
    capacity = (
        transmountain_capacity(frame, flow_rows)
        if source["name"] == "transmountain"
        else capacity_by_key_point(source, frame)
    )
    exceptions = reconciliation_exceptions(capacity)
    if exceptions.height:
        first_date = exceptions.get_column("date").min()
        last_date = exceptions.get_column("date").max()
        print(
            f"Committed/uncommitted reconciliation exceptions for {source['name']}: "
            f"{exceptions.height} rows from {first_date} through {last_date} "
            f"(tolerance {COMMITTED_VOLUME_RECONCILIATION_TOLERANCE_M3_D:,} m3/d)."
        )
    (
        capacity.select(CAPACITY_COLUMNS)
        .with_columns(pl.lit(date_transformed).alias("date_transformed"))
        .sink_csv(THROUGHPUT_STAGE_1 / str(source["capacity_filename"]))
    )
    print(f"Successfully transformed: {source['capacity_filename']}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pipeline",
        choices=[str(source["name"]) for source in CER_PIPELINE_SOURCES],
        help="Transform only this pipeline; omit to transform all sources.",
    )
    args = parser.parse_args(argv)

    THROUGHPUT_STAGE_1.mkdir(parents=True, exist_ok=True)
    for source in CER_PIPELINE_SOURCES:
        if args.pipeline is None or source["name"] == args.pipeline:
            transform_pipeline(source)


if __name__ == "__main__":
    main()
