"""
This script will function the exact same way as the
transmountain script. The mere difference is the way
the data is written. Instead of having one row with
the capacity on there, here, we have all rows with
the capacity. However, the top of the script will
be identical.
"""
from pipeline.config.settings import RAW_BUCKET, THROUGHPUT_STAGE_1, CUBIC_M_TO_BARRELS
from pipeline.config.sources import CER_PIPELINE_SOURCES

import polars as pl
import os

KEYSTONE = CER_PIPELINE_SOURCES[1]

def main():
    os.makedirs(THROUGHPUT_STAGE_1, exist_ok=True)
    
    # First we'll create a base lazy frame that we'll use for both outputs
    lf = (
        pl.scan_csv(
        source=RAW_BUCKET / KEYSTONE["raw_filename"],
        )
        .rename(
            lambda col: col
                .strip()
                .lower()
                .replace(" ", "_")
                .replace("-", "_")
                .replace("/", "_")
                .replace("(", "")
                .replace(")", "")
            )
        .select([
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
            "reason_for_variance"
        ])
        .with_columns(
            (pl.col("throughput_1000_m3_d")*1000).alias("throughput_m3_d"),
            (pl.col("throughput_1000_m3_d")*CUBIC_M_TO_BARRELS*1000).alias("throughput_barrels_d"),
            (pl.col("available_capacity_1000_m3_d")*1000).alias("available_capacity_m3_d"),
            (pl.col("available_capacity_1000_m3_d")*CUBIC_M_TO_BARRELS*1000).alias("available_capacity_barrels_d"),
        )
        .drop(["throughput_1000_m3_d", "available_capacity_1000_m3_d"])
        .with_columns(
            pl.col("pipeline")
            .str.replace_all(r"[\r\n]+", " ")
            .str.replace_all(r"\s{2,}", " ")
            .str.strip_chars()
            .str.to_titlecase().alias("pipeline")
        )
    )

    # Our flow table used for a map visual
    flow_lf = (
        lf
        .filter(pl.col("product") != 'total')
        .drop(["available_capacity_m3_d", "available_capacity_barrels_d", "reason_for_variance"])
    )

    flow_lf.sink_csv(path=THROUGHPUT_STAGE_1 / KEYSTONE["flow_locations_filename"])
    print(f"Successfully transformed: {KEYSTONE["flow_locations_filename"]}")

    """
    # Now we need to create the throughput table
    Since each row has the capacity value attached to it, we will simply take the
    first value that appears (equivalent to a SQL window function where row_num = 1).

    This may have to change in the future if we decide to include the committed and 
    uncommitted values into the database. For now, we'll keep the code simple.
    """
    throughput_lf = (
        lf
        .filter(pl.col("product") != 'total')
        .group_by(['date', 'pipeline', 'key_point'], maintain_order=True)
        .agg([
            pl.col("throughput_m3_d").sum().alias("total_throughput_m3_d"),
            pl.col("throughput_barrels_d").sum().alias("total_throughput_barrels_d"),
            pl.col("available_capacity_m3_d").first().alias("available_capacity_m3_d"),
            pl.col("available_capacity_barrels_d").first().alias("available_capacity_barrels_d"),
            pl.col("reason_for_variance").first().alias("reason_for_variance")
        ])
        .with_columns(
            (pl.col("total_throughput_m3_d") / pl.col("available_capacity_m3_d"))
            .alias("reported_available_capacity_utlization")
        )
        .rename({"key_point": "capacity_basis"})
    )

    throughput_lf.sink_csv(path=THROUGHPUT_STAGE_1 / KEYSTONE["capacity_filename"])
    print(f"Successfully transformed: {KEYSTONE["capacity_filename"]}")


if __name__ == "__main__":
    main()