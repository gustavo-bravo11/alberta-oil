"""
We will take the data from the transmountain pipeline file and 
outputted into two formats. The first will be broken down by product
and location. So essentially we can see exactly what each pipeline
was transporting and to where. The second will be a capacity table
that shows how much in total that pipeline was transporting, and
how close to capacity that was running at.
"""
from pipeline.config.settings import RAW_BUCKET, TRANSFORMED_BUCKET, CUBIC_M_TO_BARRELS
from pipeline.config.sources import CER_PIPELINE_SOURCES

import polars as pl

TRANSMOUNTAIN = CER_PIPELINE_SOURCES[2]

def main():
    # First we'll create a base lazy frame that we'll use for both outputs
    lf = (
        pl.scan_csv(
        source=RAW_BUCKET / TRANSMOUNTAIN["raw_filename"],
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

    # Our flow table used for a map visual
    flow_lf = (
        lf
        .filter(pl.col("key_point") != 'system')
        .drop(["available_capacity_m3_d", "available_capacity_barrels_d"])
    )

    flow_lf.sink_csv(
        path=TRANSFORMED_BUCKET / TRANSMOUNTAIN["flow_locations_filename"]
    )

    # Now a table with the ability to calculate utilization rate
    # To do this, we'll need to split the frame into two, then group by and sum the flows, then join
    capacity_lf = (
        lf
        .filter(pl.col("key_point") == 'system')
        .select([
            'date',
            'pipeline',
            'available_capacity_m3_d',
            'available_capacity_barrels_d'
        ])
    )

    """
        Utilization is calculated as throughput divided by reported available capacity. In some months, 
        utilization may exceed 100% because CER notes that throughput can exceed reported available 
        capacity when operating conditions change after available capacity is reported, including product 
        mix changes, unplanned outages, or downstream constraints.
    """
    total_flow_lf = (
        flow_lf.group_by(['date', 'pipeline'], maintain_order=True)
            .agg([
                pl.col("throughput_m3_d").sum().alias("total_throughput_m3_d"),
                pl.col("throughput_barrels_d").sum().alias("total_throughput_barrels_d")
            ])
    )
    throughput_lf = (
        total_flow_lf.join(
            other=capacity_lf,
            on=['date', 'pipeline'],
            validate="1:1"
        )
        .with_columns(
            (
                pl.col("total_throughput_m3_d")
                / pl.col("available_capacity_m3_d")
            ).alias("reported_available_capacity_utlization")
        )
    )

    throughput_lf.sink_csv(
        path=TRANSFORMED_BUCKET / TRANSMOUNTAIN["capacity_filename"]
    )


if __name__ == "__main__":
    main()