from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Directories for data
DATA_DIR = PROJECT_ROOT / "data"
RAW_BUCKET = DATA_DIR / "raw"
RAW_RETRIEVAL_LOG = RAW_BUCKET / "retrieval_log.csv"
VALIDATED_RAW_BUCKET = DATA_DIR / "validated"
QUARANTINE_BUCKET = DATA_DIR / "quarantine"
VALIDATION_REPORTS_BUCKET = DATA_DIR / "validation"
TRANSFORMED_BUCKET = DATA_DIR / "transformed"

# Ouput stages
THROUGHPUT_STAGE_1 = TRANSFORMED_BUCKET / "throughput_stage_1"

# Final stage-2 tables consumed by downstream analysis.
THROUGHPUT_STAGE_2_FLOW = TRANSFORMED_BUCKET / "pipeline_flow.csv"
THROUGHPUT_STAGE_2_CAPACITY = TRANSFORMED_BUCKET / "pipeline_capacity.csv"

# Constants between files
CUBIC_M_TO_BARRELS = 6.2898
