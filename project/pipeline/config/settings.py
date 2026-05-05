from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Directories for data
DATA_DIR = PROJECT_ROOT / "data"
RAW_BUCKET = DATA_DIR / "raw"
TRANSFORMED_BUCKET = DATA_DIR / "transformed"

# Constants between files
CUBIC_M_TO_BARRELS = 6.2898