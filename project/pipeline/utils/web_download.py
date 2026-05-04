"""
This will be a library for utility functions regarding downloading and saving
data files from the web. This includes as of now, CSV and Excel files, but it
is not limited from scraping data.

Many of our extraction functions will be similar so the purpose of creating this
class is to minimize the amount of code we write while ensuring all our extract
functions work in a similar fashion.
"""
import requests

from requests import Response
from bs4 import BeautifulSoup
from pathlib import Path
from urllib.parse import urljoin


def cer_extrat(url:str, extensions:tuple[str, ...], save_dir:Path) -> None:
    """
    Think of this like an orchestrator.
    Since all CER downloads are virtually identical, the only difference is
    the base link and the file type, we will use this to save ourselves
    code writing, as I have a feeling we will be using CER a lot in this project.
    """
    cer_response = safe_request_get(url=url)
    if not cer_response: return

    excel_url = find_file_url(
        response=cer_response, 
        url=url,
        extensions=extensions
    )
    if not excel_url: return

    excel_response = safe_request_get(url=excel_url)
    if not excel_response: return

    if download_file(
        response=excel_response,
        file_url=excel_url,
        output_dir=save_dir
    ):
        print("Successfully downloaded:", excel_url.split("/")[-1], "to disk.")


def download_file(response: Response, file_url:str, output_dir: Path) -> bool:
    """
    This function simply downloads the content, which comes in binary
    from the Response type, and saves it as a workbook.

    By default, if the directory does not exists, it creates it.

    @args:
        - file_url: the download link.
        - reponse: the reponse from the request method.
        - output path: where the file will be saved.

    @returns True if donwload was successful, false if an exception is caught.
    """
    file_name = file_url.split("/")[-1]
    output_path = output_dir / file_name
    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with open(output_path, "wb") as f:
            f.write(response.content)
        return True
    except PermissionError:
        print(f"Permission error for output file: {file_name}")

    except OSError:
        print(f"Disk error when writing: {file_name}")
    
    return False


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


def safe_request_get(url:str) -> Response|None:
    """
    This function wraps the request python method around a try catch block.
    This is used to ensure that the content returned from a request is appropriate.
    
    @args: url -> The string to request
    @returns: Response, contains content, text, headers of the requested page
              None if an exception is caught and prints error to console
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