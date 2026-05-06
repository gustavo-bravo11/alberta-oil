"""
This script will transform the raw data from
the Enbridge Canadian Mainline throuput file.
The Enbridge data is much different due to the size of this
pipeline system. The capacity differs at different key points,
so instead of breaking the capacity down at the pipeline
level, we will have to use the key point column. 

Additionaly, we need to exclude the rows that do not include the capacity.
Enbridge does a good job at ensuring the row matches the capacity,
but my assumption is that when the capacity is low, and it's a short
distance, they do not include the PL capacity. We will retain it
in the flows, but not for the utilization rate calculation.
"""
from pipeline.config.settings import RAW_BUCKET, TRANSFORMED_BUCKET, CUBIC_M_TO_BARRELS
from pipeline.config.sources import CER_PIPELINE_SOURCES

import polars as pl

ENBRIDGE = CER_PIPELINE_SOURCES[0]

def main():
    # We need to drop the system row because it's basically useless here
    lf = (
        pl.scan_csv(
        source=RAW_BUCKET / ENBRIDGE["raw_filename"],
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
            "available_capacity_1000_m3_d"
        ])
        .filter(
            (pl.col("key_point") != "system") &
            pl.col("available_capacity_1000_m3_d").is_not_null()
        )
        .with_columns(
            (pl.col("throughput_1000_m3_d")*1000).alias("throughput_m3_d"),
            (pl.col("throughput_1000_m3_d")*CUBIC_M_TO_BARRELS*1000).alias("throughput_barrels_d"),
            (pl.col("available_capacity_1000_m3_d")*1000).alias("available_capacity_m3_d"),
            (pl.col("available_capacity_1000_m3_d")*CUBIC_M_TO_BARRELS*1000).alias("available_capacity_barrels_d"),
        )
        .drop(["throughput_1000_m3_d", "available_capacity_1000_m3_d"])
        .with_columns(
            pl.col("pipeline").str.to_titlecase().alias("pipeline")
        )
    )

    flow_lf = (
        lf
        .filter(pl.col("key_point") != 'system')
        .drop(["available_capacity_m3_d", "available_capacity_barrels_d"])
    )

    flow_lf.sink_csv(path=TRANSFORMED_BUCKET / ENBRIDGE["flow_locations_filename"])
    print(f"Successfully transformed: {ENBRIDGE["flow_locations_filename"]}")

    """
    # Now we need to create the throughput table
    Since each row has the capacity value attached to it, we will simply take the
    first value that appears (equivalent to a SQL window function where row_num = 1).

    This may have to change in the future if we decide to include the committed and 
    uncommitted values into the database. For now, we'll keep the code simple.
    """
    throughput_lf = (
        lf
        .filter(
            (pl.col("product") != 'total') &
            pl.col("throughput_m3_d").is_not_null() &
            (pl.col("key_point") == "ex-Gretna")
        )
        .group_by(['date', 'pipeline', 'key_point'], maintain_order=True)
        .agg([
            pl.col("throughput_m3_d").sum().alias("total_throughput_m3_d"),
            pl.col("throughput_barrels_d").sum().alias("total_throughput_barrels_d"),
            pl.col("available_capacity_m3_d").first().alias("available_capacity_m3_d"),
            pl.col("available_capacity_barrels_d").first().alias("available_capacity_barrels_d")
        ])
        .with_columns(
            (pl.col("total_throughput_m3_d") / pl.col("available_capacity_m3_d"))
            .alias("reported_available_capacity_utlization")
        )
        .rename({"key_point": "capacity_basis"})
    )

    throughput_lf.sink_csv(path=TRANSFORMED_BUCKET / ENBRIDGE["capacity_filename"])
    print(f"Successfully transformed: {ENBRIDGE["capacity_filename"]}")


if __name__ == "__main__":
    main()