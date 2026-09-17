"""Extract the one-time NRCan GeoJSON snapshot for the Trans Mountain pipeline.

This source is static reference data rather than a live feed. It is therefore
available as its own manually invoked orchestrator task and is intentionally
excluded from the scheduled/default extraction stages.
"""

from __future__ import annotations

from pipeline.config.settings import RAW_BUCKET, RAW_RETRIEVAL_LOG
from pipeline.config.sources import (
    NRCAN_TM_BASE_URL,
    NRCAN_TM_QUERY_PARAMS,
    NRCAN_TM_SOURCES,
)
from pipeline.utils.run_context import RunContext
from pipeline.utils.web_download import download_file, record_retrieval, safe_request_get


def layer_query_url(layer_id: int) -> str:
    """Return the ArcGIS query endpoint for one configured layer."""
    return f"{NRCAN_TM_BASE_URL}/{layer_id}/query"


def extract_source(source: dict[str, str | int], context: RunContext) -> bool:
    """Download and record one configured NRCan GeoJSON layer."""
    source_name = str(source["name"])
    raw_filename = str(source["raw_filename"])
    response = safe_request_get(
        layer_query_url(int(source["layer_id"])),
        params=NRCAN_TM_QUERY_PARAMS,
    )
    if not response:
        return False

    if not download_file(
        response=response,
        file_url=response.url,
        output_name=raw_filename,
        output_dir=RAW_BUCKET,
    ):
        return False

    record_retrieval(
        source_name=source_name,
        raw_filename=raw_filename,
        retrieval_log=RAW_RETRIEVAL_LOG,
        run_id=context.run_id,
        run_type=context.run_type,
    )
    print("Successfully downloaded:", raw_filename, "to disk.")
    return True


def main(run_id: str | None = None, run_type: str = "forced") -> None:
    """Download every configured one-time Trans Mountain GeoJSON layer."""
    context = RunContext(run_id, run_type) if run_id else RunContext.create(run_type)
    failed_sources = [
        str(source["name"])
        for source in NRCAN_TM_SOURCES
        if not extract_source(source, context)
    ]
    if failed_sources:
        raise RuntimeError("Extraction failed for: " + ", ".join(failed_sources) + ".")


if __name__ == "__main__":
    main()
