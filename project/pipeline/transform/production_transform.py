"""
Loading script for the production data from the Canada Energy
Regulator. We will only take the cubic meter to avoid storing
the data in multiple formats. We can change this later.

The data will read the file the sheet "HIST - cubic meters per day".
And then take the columns for alberta. Mostly, conventional oil both
light and heavy, and the oil sands columns.

This transformation step will use polars to create the "tables".
For simplicity, we will just have a CSV table database.
"""
import polars as pl
from pathlib import Path

FILENAME = "estimated-production-canadian-crude-oil-equivalent.xlsx"
SHEET_NAME = "HIST - cubic meters per day"
RAW_BUCKET = Path("../../data/raw")
TRANSFORMED_BUCKET = Path("../../data/transformed")
CUBIC_M_TO_BARRELS = 6.2898

def main():
    file_path = RAW_BUCKET / FILENAME
    df = pl.read_excel(
        file_path, 
        sheet_name=SHEET_NAME,
        engine='xlsx2csv',
        drop_empty_cols=True,
        infer_schema_length=10000
        )

    # Clean column names and select our colunms
    df = df.rename(
        lambda col: col.strip().lower().replace(" ", "_")
        ).select([
            pl.col('month').str.strptime(pl.Date, '%b-%y'),
            pl.col('sk_light').cast(pl.Float64),
            pl.col('sk_heavy').cast(pl.Float64),
            pl.col('ab_conv_light').cast(pl.Float64),
            pl.col('ab_conv_heavy').cast(pl.Float64),
            pl.col('ab_upgraded').cast(pl.Float64),
            pl.col('ab_non-upgraded').cast(pl.Float64),
            pl.col('ab_cond').cast(pl.Float64),
        ])

    pivoted_output_name = "AB_SK_cubic_meters_per_day.csv"
    df.write_csv(
        file= TRANSFORMED_BUCKET / pivoted_output_name
    )

    """
        Now we pivot the data to long format for our actual table, 
        we also converting it to barrels.
        Lastly, we'll add a mapping to facilitate filtering,
        this categorizes the oil by how difficult it is to move.
        More viscous oils, such as the non-upgrade oil sands require
        more processing to move. This will be vital to our analysis.

        Logic for constraint category column->
            Heavy or non-upgrade is hard to move so = constrained
            Upgrade slightly difficult still but easier = semi-constrained
            Light = unconstrained
            Cond not relevant to our issues = support
            Else = other
    """
    unpivoted_df = df.unpivot(
        on=['sk_light', 'sk_heavy', 'ab_conv_light', 'ab_conv_heavy', 'ab_upgraded', 'ab_non-upgraded', 'ab_cond'],
        index='month',
        variable_name='oil_type',
        value_name='avg_cubic_meters_per_day',   
    ).filter(
        pl.col('avg_cubic_meters_per_day').is_not_null()
    ).with_columns(
        (pl.col('avg_cubic_meters_per_day')*CUBIC_M_TO_BARRELS).alias('avg_barrels_per_day')
    ).with_columns(
        pl.when(
            pl.col('oil_type').str.contains('heavy') | 
            pl.col('oil_type').str.contains('non-upgraded'))
        .then(pl.lit('constrained'))
        .when(pl.col('oil_type').str.contains('upgraded'))
        .then(pl.lit('semi-constained'))
        .when(pl.col('oil_type').str.contains('light'))
        .then(pl.lit('unconstrained'))
        .when(pl.col('oil_type').str.contains('cond'))
        .then(pl.lit('support'))
        .otherwise(pl.lit('other'))
        .alias('constraint_category')
    )

    unpivoted_ouput_name = "AB_SK_production.csv"
    unpivoted_df.write_csv(
        file=TRANSFORMED_BUCKET / unpivoted_ouput_name
    )

if __name__ == "__main__":
    main()