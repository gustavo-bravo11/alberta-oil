"""
This will be a library for utility functions regarding downloading and saving
data files from the web. This includes as of now, CSV and Excel files, but it
is not limited from scraping data.

Many of our extraction functions will be similar so the purpose of creating this
class is to minimize the amount of code we write while ensuring all our extract
functions work in a similar fashion.
"""
import csv
from collections.abc import Mapping
from datetime import datetime, timezone

import requests

from requests import Response
from bs4 import BeautifulSoup
from pathlib import Path
from urllib.parse import urljoin


def download_file(
        response: Response, 
        file_url:str, 
        output_name:str,
        output_dir: Path) -> bool:
    """
    This function simply downloads the content, which comes in binary
    from the Response type, and saves it as a workbook.

    By default, if the directory does not exists, it creates it.

    @args:
        - file_url: the download link.
        - reponse: the reponse from the request method.
        - output_name: the name of the saved file.
        - output path: where the file will be saved.

    @returns True if donwload was successful, false if an exception is caught.
    """
    output_path = output_dir / output_name
    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with open(output_path, "wb") as f:
            f.write(response.content)
        return True
    except PermissionError:
        print(f"Permission error for output file: {output_name}")

    except OSError:
        print(f"Disk error when writing: {output_name}")
    
    return False


def record_retrieval(
    source_name: str,
    raw_filename: str,
    retrieval_log: Path,
    run_id: str,
    run_type: str,
) -> None:
    """Append the UTC retrieval timestamp for one successfully saved raw file."""
    if run_type not in {"forced", "scheduled"}:
        raise ValueError("run_type must be 'forced' or 'scheduled'.")
    retrieval_log.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ("source_name", "raw_filename", "date_retrieved_utc", "run_id", "run_type")
    existing_rows: list[dict[str, str]] = []
    write_header = not retrieval_log.exists() or retrieval_log.stat().st_size == 0
    if retrieval_log.exists() and retrieval_log.stat().st_size > 0:
        with retrieval_log.open("r", newline="", encoding="utf-8") as log_file:
            reader = csv.DictReader(log_file)
            existing_rows = list(reader)
            existing_fields = reader.fieldnames or []
        if tuple(existing_fields) != fieldnames:
            # Historical rows predate run tracking; preserve them with blank new fields.
            with retrieval_log.open("w", newline="", encoding="utf-8") as log_file:
                writer = csv.DictWriter(log_file, fieldnames=fieldnames)
                writer.writeheader()
                for row in existing_rows:
                    writer.writerow({field: row.get(field, "") for field in fieldnames})
            write_header = False
    with retrieval_log.open("a", newline="", encoding="utf-8") as log_file:
        writer = csv.DictWriter(
            log_file,
            fieldnames=fieldnames,
        )
        if write_header:
            writer.writeheader()
        writer.writerow(
            {
                "source_name": source_name,
                "raw_filename": raw_filename,
                "date_retrieved_utc": datetime.now(timezone.utc).isoformat(),
                "run_id": run_id,
                "run_type": run_type,
            }
        )


def find_file_url(response:Response, url:str, extensions:tuple[str, ...]) -> str|None:
    """
    This function's purpose is to return a file found on a website. For now,
    we will not worry about finding multiple files.
    
    This function converts the passed in Response object and converts it into a
    searchable object using the beautiful soup library, then looks through
    the html content for an <a> tag with an href that ends with the file
    extension passed.

    So for example an excel file in the website may look like
    <a href="file_to_download.xlsx">Button</a>. So our scraper will
    find the xlsx extension, and return the link attached to it.

    @args: 
        - Reponse -> the response object from the request
        - url -> the main url to append the file once found
        - extensions -> tuple containing the valid file extensions
    
    @returns full link to downloadable file or None if file with the
        valid extensions is not found.
    """
    soup = BeautifulSoup(response.text, "html.parser")

    for link in soup.find_all("a"):
        href = link.get("href")

        if isinstance(href, str) and href.endswith(extensions):
            return urljoin(url, href)
        
    return None


def safe_request_get(
    url: str,
    *,
    params: Mapping[str, str] | None = None,
    timeout: float = 30,
) -> Response | None:
    """
    This function wraps the request python method around a try catch block.
    This is used to ensure that the content returned from a request is appropriate.
    
    @args: url -> The string to request
    @returns: Response, contains content, text, headers of the requested page
              None if an exception is caught and prints error to console
    """
    try:
        response = requests.get(url, params=params, timeout=timeout)
        
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
