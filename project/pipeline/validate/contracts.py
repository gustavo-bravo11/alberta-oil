"""Executable definitions for pipeline-throughput input contracts."""

from __future__ import annotations

from dataclasses import dataclass


CONTRACT_VERSION = "2026-09-14"
ALLOWED_PRODUCTS = frozenset(
    {
        "domestic heavy",
        "domestic light",
        "domestic light / ngl",
        "foreign light",
        "refined petroleum products",
        "total",
    }
)
ALLOWED_DIRECTIONS = frozenset({"north", "south", "east", "west"})
ALLOWED_TRADE_TYPES = frozenset(
    {"import", "export", "intracanada", "intracanada / export"}
)

COMMON_COLUMNS = (
    "Date",
    "Month",
    "Year",
    "Company",
    "Pipeline",
    "Key Point",
    "Latitude",
    "Longitude",
    "Direction Of Flow",
    "Trade Type",
    "Product",
    "Throughput (1000 m3/d)",
    "Nameplate Capacity (1000 m3/d)",
    "Available Capacity (1000 m3/d)",
    "Reason For Variance",
)


@dataclass(frozen=True)
class ThroughputContract:
    """Rules that vary among the three CER pipeline sources."""

    source_name: str
    raw_filename: str
    company: str
    pipeline: str
    required_columns: tuple[str, ...]
    unique_key: tuple[str, ...]
    key_points: frozenset[str] | None = None


CONTRACTS = {
    "enbridge_mainline": ThroughputContract(
        source_name="enbridge_mainline",
        raw_filename="enbridge_throughput_details.csv",
        company="Enbridge Pipelines Inc.",
        pipeline="Enbridge Canadian Mainline system",
        required_columns=COMMON_COLUMNS,
        unique_key=("Date", "Pipeline", "Key Point", "Product", "Trade Type"),
    ),
    "keystone": ThroughputContract(
        source_name="keystone",
        raw_filename="keystone_throughput_details.csv",
        company="South Bow GP (Canada) Ltd.",
        pipeline="Keystone pipeline",
        required_columns=(
            *COMMON_COLUMNS[:12],
            "Committed Volumes (1000 m3/d)",
            "Uncommitted Volumes (1000 m3/d)",
            *COMMON_COLUMNS[12:],
        ),
        unique_key=("Date", "Pipeline", "Key Point", "Product"),
        key_points=frozenset({"International boundary at or near Haskett, Manitoba"}),
    ),
    "transmountain": ThroughputContract(
        source_name="transmountain",
        raw_filename="transmountain_throughput_details.csv",
        company="Trans Mountain Pipeline ULC",
        pipeline="Trans Mountain pipeline",
        required_columns=(
            *COMMON_COLUMNS[:12],
            "Committed Volumes (1000 m3/d)",
            "Uncommitted Volumes (1000 m3/d)",
            *COMMON_COLUMNS[12:],
        ),
        unique_key=("Date", "Pipeline", "Key Point", "Product"),
        key_points=frozenset({"Burnaby", "Sumas", "Westridge", "system"}),
    ),
}
