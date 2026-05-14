"""
The goal of this script is to normalize the
categories, and file formats of the columns
from all throughput files, then combine them together into one csv.

This script will output two files, the flow locations, and the
capacity based files.

The resulting output will be what gets loaded into the database.

Goal, create two functions here, or script, which can be execute in parallel.
"""
from pipeline.config.settings import THROUGHPUT_STAGE_1, THROUGHPUT_STAGE_2_FLOW, THROUGHPUT_STAGE_2_CAPACITY
import polars as pl

# Used to shorten the pipeline names
PIPELINE_MAP = {
    "enbridge canadian mainline system": "enbridge_mainline",
    "keystone pipeline": "keystone",
    "trans mountain pipeline": "trans_mountain",
}

def main() -> None:
    """
    Concatenate all frames into two lazy frames by looping
    through all the files in the directory which contain
    the types below. Then create a main lazy frame for each.
    """
    table_types = ['flow_location', 'capacity']
    table_frames = []

    for table_type in table_types:
        frames = []
        for path in THROUGHPUT_STAGE_1.glob(f"*{table_type}.csv"):
            frames.append(
                pl.scan_csv(path, try_parse_dates=True)
            )
        table_frames.append(pl.concat(frames, how='diagonal'))

    """
    Now we manipulate both to actually normalize them.
    
    Starts with the flow table
    """
    flow_frame = table_frames[0]

    """
    Transformations:
        - Clean and standardize to create a new column for:
            pipeline, key_point, and trade_type.
            Some of these are shortened, but for the most part
            we just remove spaces and non-alphanumeric characters
        - Add an original tag to the unchanged versions of these
        - Adjust the order of the columns
    """
    flow_frame_standard = (
        flow_frame
        .with_columns(
            pl.col('pipeline')
                .str.to_lowercase()
                .str.strip_chars()
                .replace(PIPELINE_MAP)
                .alias("pipeline_standard"),

            pl.col('key_point')
                .str.to_lowercase()
                .replace("international boundary at or near haskett, manitoba", "haskett_border")
                .str.replace_all(r"[^A-Za-z0-9]+", "_")
                .str.strip_chars("_")
                .alias("key_point_standard"),

            pl.col('product').str.replace_all(r"\s\W*", "_"),

            pl.when((pl.col('trade_type') == 'intracanada / export'))
                .then(pl.lit('mixed_intracanada_export'))
                .otherwise(
                    pl.col('trade_type')
                    .str.to_lowercase()
                    .str.replace_all(r"[^A-Za-z0-9]+", "_")
                    .str.strip_chars("_")
                )
                .alias('trade_type_standard'),
        )
        .rename({
            "trade_type": "trade_type_original",
            "key_point": "key_point_original",
            "pipeline": "pipeline_original",
        })
        .select([
            'date', 
            'pipeline_original', 
            'pipeline_standard', 
            'key_point_original', 
            'key_point_standard', 
            'trade_type_original', 
            'trade_type_standard',
            'product',
            'direction_of_flow', 
            'latitude', 
            'longitude', 
            'throughput_m3_d', 
            'throughput_barrels_d', 
        ])
        .sort(['date', 'pipeline_standard'], descending=[True, False])
    )

    flow_frame_standard.sink_csv(path=THROUGHPUT_STAGE_2_FLOW)
    print("Successfully transfomed:", THROUGHPUT_STAGE_2_FLOW)

    """
    Now for the capacity data.
    """
    capacity_frame = table_frames[1]

    capacity_frame_standard = (
        capacity_frame
        .with_columns(
            pl.col('pipeline')
                .str.to_lowercase()
                .str.strip_chars()
                .replace(PIPELINE_MAP)
                .alias("pipeline_standard"),

            pl.col('capacity_basis')
                .str.to_lowercase()
                .replace("international boundary at or near haskett, manitoba", "haskett_border")
                .str.strip_chars()
                .str.strip_chars("_")
                .alias('capacity_basis_standard'),
            
            pl.col('reason_for_variance')
                .str.strip_chars()
                .replace(
                    'Capacity may vary month to month based on NEB Regulatory Directive, Downstream Restrictions, Curtailment/Interruptions, Force Majeure and System Operating Factor',
                    None
                )
                .replace(
                    'Capacity may vary month to month based on CER Regulatory Directive, Downstream Restrictions, Curtailment/Interruptions, Force Majeure and System Operating Factor',
                    None
                )
                .str.replace_all(r"\s*[,;]\s*", ", ")
                .str.to_uppercase()
                .alias('reason_for_variance')
        )
        .rename({
            "pipeline": "pipeline_original",
            "capacity_basis": "capacity_basis_original",
        })
        .select([
            'date', 
            'pipeline_original', 
            'pipeline_standard',
            'capacity_basis_original', 
            'capacity_basis_standard',
            'total_throughput_m3_d', 
            'total_throughput_barrels_d', 
            'available_capacity_m3_d', 
            'available_capacity_barrels_d', 
            'reported_available_capacity_utlization', 
            'reason_for_variance', 
        ])
        .sort(['date', 'pipeline_standard'], descending=[True, False])
    )

    capacity_frame_standard.sink_csv(path=THROUGHPUT_STAGE_2_CAPACITY)
    print("Successfully transformed:", THROUGHPUT_STAGE_2_CAPACITY)

if __name__ == "__main__":
    main()