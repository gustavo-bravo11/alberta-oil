from pipeline.config.settings import RAW_BUCKET, TRANSFORMED_BUCKET, CUBIC_M_TO_BARRELS
from pipeline.config.sources import CER_RAIL_EXPORTS

import polars as pl
import unicodedata

MONTH_NUM = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}

def main():
    df = (
        pl.read_excel(
            source=RAW_BUCKET/CER_RAIL_EXPORTS["raw_filename"],
            engine="calamine",
            read_options={
                "header_row": 7,
                "use_columns": "B:G"
            }
        )
        .rename(clean_column_names)
        .with_columns(
            # Even though this dataset comes with barrels, we'll still convert to keep consistent
            ((pl.col('volume_m3_per_day'))*CUBIC_M_TO_BARRELS).alias('volume_barrels_per_day'),
            pl.col('year').forward_fill()
        )
        .with_columns(
            pl.date(
                year=pl.col('year').cast(pl.Int32),
                month=(
                    pl.col('month').str.strip_chars().str.to_lowercase()
                        .replace(MONTH_NUM).cast(pl.Int8)
                ),
                day=1
            )
            .alias('date')
        )
        .select([
            'date', 'volume_m3_per_day'
        ])
    )

    df.write_csv(
        file=TRANSFORMED_BUCKET/CER_RAIL_EXPORTS['output_filename']
    )
    print("Successfully transformed:", TRANSFORMED_BUCKET/CER_RAIL_EXPORTS['output_filename'])


def clean_column_names(col:str) -> str:
    """
    This helper function converts any non-standard unicode character into a standard version of it.
    In essance, it will convert a superscript into a regular script.
    It also: converts it to lower case, strips whitespace, removes spaces for underscore,
    gets rids of brackets, and get's rid of new lines
    """
    return unicodedata.normalize("NFKD", col)\
            .lower()\
            .strip()\
            .replace(" ", "_")\
            .replace("(", "").replace(")", "")\
            .replace("\n", "_")

if __name__ == "__main__":
    main()