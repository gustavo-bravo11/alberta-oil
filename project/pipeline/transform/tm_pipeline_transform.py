"""
We will take the data from the transmountain pipeline file and 
outputted into two formats. The first will be broken down by product
and location. So essentially we can see exactly what each pipeline
was transporting and to where. The second will be a capacity table
that shows how much in total that pipeline was transporting, and
how close to capacity that was running at.
"""
from pathlib import Path
import polars as pl

FILENAME = "trans-mountain-throughput-and-capacity.csv"
RAW_BUCKET = Path("data/raw")


def main():
    lf = pl.scan_csv(RAW_BUCKET/FILENAME)

if __name__ == "__main__":
    main()