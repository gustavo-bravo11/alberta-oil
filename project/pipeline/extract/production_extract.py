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
PRODCUTION_DATA_URL = "https://www.cer-rec.gc.ca/en/data-analysis/energy-commodities/crude-oil-petroleum-products/statistics/estimated-production-canadian-crude-oil-equivalent.html"
RAW_BUCKET = Path("data/raw")

def main():
    """
    Open the CER website, look for the xlsx file, then get the 
    file content and write it to disk.
    """
    cer_response = safe_request_get(url=PRODCUTION_DATA_URL)
    if not cer_response: return

    excel_url = find_file_url(
        response=cer_response, 
        url=PRODCUTION_DATA_URL,
        extensions=("xlsx", "xls")
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