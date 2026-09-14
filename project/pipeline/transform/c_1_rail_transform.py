from pipeline.config.settings import RAW_BUCKET, TRANSFORMED_BUCKET, CUBIC_M_TO_BARRELS
from pipeline.config.sources import CER_RAIL_EXPORTS
from pipeline.utils.timestamps import current_utc_timestamp

import fastexcel
import polars as pl
import re
import unicodedata
from datetime import date, datetime, timezone
from pathlib import Path

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

SOURCE_DATE_FORMATS = (
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%B %d, %Y",
    "%b %d, %Y",
    "%d %B %Y",
    "%d %b %Y",
)
DATE_PATTERNS = (
    r"\d{4}[-/]\d{1,2}[-/]\d{1,2}",
    r"[A-Za-z]+\s+\d{1,2},?\s+\d{4}",
    r"\d{1,2}\s+[A-Za-z]+\s+\d{4}",
)


def normalize_source_datetime(value: object) -> str:
    """Normalize a workbook update value to an ISO-8601 UTC datetime string."""
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value, datetime.min.time())
    else:
        text = str(value).strip()
        candidates = [text]
        candidates.extend(
            match.group(0)
            for pattern in DATE_PATTERNS
            if (match := re.search(pattern, text)) is not None
        )
        for candidate in candidates:
            try:
                parsed = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
                break
            except ValueError:
                pass
            for date_format in SOURCE_DATE_FORMATS:
                try:
                    parsed = datetime.strptime(candidate, date_format)
                    break
                except ValueError:
                    continue
            else:
                continue
            break
        else:
            raise ValueError(f"Could not parse rail source update date: {text!r}")

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


def read_rail_sheet(workbook_path: Path, **read_options: object) -> pl.DataFrame:
    """Read the configured rail worksheet with an explicit Arrow-to-DataFrame conversion."""
    reader = fastexcel.read_excel(workbook_path)
    worksheet = reader.load_sheet(str(CER_RAIL_EXPORTS["sheet_name"]), **read_options)
    return pl.DataFrame(worksheet)


def source_last_updated(workbook_path: Path) -> str:
    """Read the rail workbook's visible 'Last updated' value."""
    metadata = read_rail_sheet(
        workbook_path,
        header_row=None,
        use_columns="A:H",
    )
    for row in metadata.rows():
        for index, value in enumerate(row):
            if value is None:
                continue
            match = re.search(
                r"(?:numbers\s+)?last\s+updated(?:\s+on)?\s*:?\s*(.*)",
                str(value),
                re.IGNORECASE,
            )
            if match is None:
                continue
            date_value: object = match.group(1).strip()
            if not date_value and index + 1 < len(row):
                date_value = row[index + 1]
            if date_value:
                return normalize_source_datetime(date_value)
    raise ValueError(f"No 'Last updated' value found in {workbook_path.name}.")

def main():
    TRANSFORMED_BUCKET.mkdir(parents=True, exist_ok=True)
    raw_file = RAW_BUCKET / CER_RAIL_EXPORTS["raw_filename"]
    source_updated_at = source_last_updated(raw_file)
    date_transformed = current_utc_timestamp()
    df = (
        read_rail_sheet(
            raw_file,
            header_row=7,
            use_columns="B:G",
        )
        .rename(clean_column_names)
        .filter(
            pl.col('month')
            .cast(pl.String)
            .str.strip_chars()
            .str.to_lowercase()
            .is_in(list(MONTH_NUM))
        )
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
        .with_columns(
            pl.lit(source_updated_at).alias('source_last_updated'),
            pl.lit(date_transformed).alias('date_transformed'),
        )
        .select([
            'date',
            'volume_m3_per_day',
            'volume_barrels_per_day',
            'source_last_updated',
            'date_transformed',
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
