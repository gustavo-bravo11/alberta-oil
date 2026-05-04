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
    - North American Crude Oil Refinery

This file will be used to extract the data from this website. Since the file
is available via spreadsheets, we have to scrape the website, to find the
latest available data.
"""
from pipeline.utils.web_download import safe_request_get, download_file, find_file_url
from pathlib import Path

# Constants, pages and output directory
RAW_BUCKET = Path("data/raw")

SOURCES = [
    {
        "name": "estimated_production",
        "url": "https://www.cer-rec.gc.ca/en/data-analysis/energy-commodities/crude-oil-petroleum-products/statistics/estimated-production-canadian-crude-oil-equivalent.html",
        "file_extensions": (".xlsx", ".xls")
    },
    {
        "name": "enbridge_mainline_pipeline",
        "url": "https://open.canada.ca/data/en/dataset/dc343c43-a592-4a27-8ee7-c77df56afb34/resource/a3877960-65f2-47d0-9886-688ba1cabddc",
        "file_extensions": (".csv",)
    },
    {
        "name": "keystone_pipeline",
        "url": "https://open.canada.ca/data/en/dataset/dc343c43-a592-4a27-8ee7-c77df56afb34/resource/b7597d90-0d9a-44d8-8d31-3434d693d6d9",
        "file_extensions": (".csv",)
    },
    {
        "name": "transmountain_pipeline",
        "url": "https://open.canada.ca/data/en/dataset/dc343c43-a592-4a27-8ee7-c77df56afb34/resource/404fa9e0-73b1-4a8c-9f43-8045d7edb426",
        "file_extensions": (".csv",)
    },
]

def main():
    """
    Open the CER website, look for the xlsx file, then get the 
    file content and write it to disk.
    """
    for source in SOURCES:
        cer_response = safe_request_get(url=source["url"])
        if not cer_response: return

        excel_url = find_file_url(
            response=cer_response, 
            url=source["url"],
            extensions=source["file_extensions"]
        )
        if not excel_url: return

        excel_response = safe_request_get(url=excel_url)
        if not excel_response: return

        if download_file(
            response=excel_response,
            file_url=excel_url,
            output_dir=RAW_BUCKET
        ):
            print("Successfully downloaded:", excel_url.split("/")[-1], "to disk.")

if __name__ == "__main__":
    main()