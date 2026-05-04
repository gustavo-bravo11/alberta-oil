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
from pathlib import Path
from bs4 import BeautifulSoup
from urllib.parse import urljoin

import requests
from requests import Response

# Constants, pages and output directory
PRODCUTION_DATA_URL = "https://www.cer-rec.gc.ca/en/data-analysis/energy-commodities/crude-oil-petroleum-products/statistics/estimated-production-canadian-crude-oil-equivalent.html"
RAW_BUCKET = Path("../../data/raw")

def main():
    html = get_html(PRODCUTION_DATA_URL)

    if not html:
        print("Failed to fetch valid html file")
        return
    
    excel_url = get_excel_url(html, PRODCUTION_DATA_URL)

    if not excel_url:
        print("Failed to get excel url for production data")
        return

    output_file_name = "Estimated Oil Production Canada"

    if download_excel(excel_url):
        print(f"Successfully downloaded: {output_file_name}")


def download_excel(excel_url:str) -> bool:
    """
    This helper function accesses the excel URL and writes it
    into the disk. It uses the constant to know where the write bucket.
    """
    response = safe_request_get(excel_url)

    if not response:
        return False

    # This extracts the file name from the URL
    file_name = excel_url.split("/")[-1]
    output_path = RAW_BUCKET / file_name

    try:
        with open(output_path, "wb") as f:
            f.write(response.content)
        return True
    
    except PermissionError:
        print(f"Permission error for output file: {file_name}")

    except OSError:
        print(f"Disk error when writing: {file_name}")
    
    return False


def get_excel_url(html:str, page_url:str) -> str|None:
    """
    This helper function finds the excel file given in the
    url. This function is only currently built for the excel file
    in the production case, and other cases have not been explored.
    """
    # Converts the html string into a searchable element
    soup = BeautifulSoup(html, "html.parser")
    
    # Now we need to find a link which is an <a href=""> tag
    # This can be made easier because we know it's an xlsx file
    for link in soup.find_all("a"):
        href = link.get("href")

        if isinstance(href, str) and href.endswith((".xlsx", "xls")):
            # Returns a relative link so we need to add them together
            return urljoin(page_url, href)
        
    return None


def get_html(page_url:str) -> None|str:
    """Get the html page from CER."""
    response = safe_request_get(page_url)
    if response:
        return response.text
    else:
        return None

    
def safe_request_get(url:str) -> Response|None:
    """
    This method wraps the request python method around a try catch block.
    This is used to ensure that html and excel content requests return
    the appropriate content.
    """
    try:
        response = requests.get(url)
        
        # This line converts 404 and 500 errors into exceptions
        response.raise_for_status()
        return response

    except requests.exceptions.Timeout:
        print(f"Timeout while fetching {url}")
        return None
    
    except requests.exceptions.ConnectionError:
        print(f"Connection error - verify the URL or the network connection:{url}")
        return None
    
    except requests.exceptions.HTTPError as e:
        "These are 404 (Not found) or 500 (Failed to fetch) error"
        print(f"HTTP error on: {e}")
        return None
    
    except requests.exceptions.RequestException as e:
        print(f"Unexpected request error: {e}")
        return None


if __name__ == "__main__":
    main()