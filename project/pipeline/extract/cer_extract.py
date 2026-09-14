"""
This script will extract data from the Canada Energy Regulator (CER) website,
or https://www.cer-rec.gc.ca/en/data-analysis/energy-commodities/crude-oil-petroleum-products/
To start we wil scrape the data from the available spreadsheets of:
    - Canadian Crude Oil Exports by Rail - Monthly Data
        We know that Alberta's biggest block from being an exporter is: its
        lack of access to the sea (landlocked) and its lack of infrastucture
        to ship oil (this could be eastern Canada, western Canada, or America).
        When our pipelines hit capacity, and they often due, this number should
        in theory go up.

    - Estimated Production of Canadian Crude Oil and Equivalent
    - Crude Oil Export Summary
    - North American Crude Oil Refinery - Not Implemmented

This file will be used to extract the data from this website. Since the file
is available via spreadsheets, we have to scrape the website, to find the
latest available data.
"""
from pipeline.utils.web_download import (
    download_file,
    find_file_url,
    record_retrieval,
    safe_request_get,
)
from pipeline.config.sources import CER_PRODUCTION, CER_PIPELINE_SOURCES, CER_RAIL_EXPORTS
from pipeline.config.settings import RAW_BUCKET, RAW_RETRIEVAL_LOG

from pathlib import Path


def main() -> None:
    """
    Open the CER website, look for the xlsx file, then get the 
    file content and write it to disk.

    Does this for all the files in the sources by appending each list together.
    """
    sources = [CER_PRODUCTION] + CER_PIPELINE_SOURCES + [CER_RAIL_EXPORTS]

    failed_sources: list[str] = []
    for source in sources:
        cer_response = safe_request_get(url=source["source_page_url"])
        if not cer_response:
            failed_sources.append(str(source["name"]))
            continue

        excel_url = find_file_url(
            response=cer_response, 
            url=source["source_page_url"],
            extensions=source["file_extensions"]
        )
        if not excel_url:
            print(f"No supported download link found for: {source['name']}")
            failed_sources.append(str(source["name"]))
            continue

        excel_response = safe_request_get(url=excel_url)
        if not excel_response:
            failed_sources.append(str(source["name"]))
            continue

        if download_file(
            response=excel_response,
            file_url=excel_url,
            output_name=source["raw_filename"],
            output_dir=RAW_BUCKET
        ):
            record_retrieval(
                source_name=str(source["name"]),
                raw_filename=str(source["raw_filename"]),
                retrieval_log=RAW_RETRIEVAL_LOG,
            )
            print("Successfully downloaded:", source["raw_filename"], "to disk.")
        else:
            failed_sources.append(str(source["name"]))

    if failed_sources:
        raise RuntimeError(
            "Extraction failed for: " + ", ".join(failed_sources) + ". Transform tasks were not run."
        )

if __name__ == "__main__":
    main()
