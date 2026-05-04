"""
This script will extract the CSV files containing the pipeline
oil throughput data from the Canada Energy Regulator.
Pipeline data for oil commodities is updated once monthly, this
is what we care the most about. For the sake of simplicity,
we will only look at the 4 largest exporting pipelines
from Alberta. This accounts for the majority of our oil being
exported, these are:
    - Enbridge Canadian Mainline: Largest crude export route (58%)
    - Keystone: Carries Alberta crude into the US market
    - Trans Mountain: BC pipeline

These are separate files and thus will require their own extraction
processes, they will be dumped into the raw bucket independently
The main site is 
https://open.canada.ca/data/en/dataset/dc343c43-a592-4a27-8ee7-c77df56afb34
"""
from pathlib import Path
from bs4 import BeautifulSoup
from urllib.parse import urljoin

import requests

ENRBRIDGE = "https://open.canada.ca/data/en/dataset/dc343c43-a592-4a27-8ee7-c77df56afb34/resource/a3877960-65f2-47d0-9886-688ba1cabddc"
KEYSTONE = "https://open.canada.ca/data/en/dataset/dc343c43-a592-4a27-8ee7-c77df56afb34/resource/b7597d90-0d9a-44d8-8d31-3434d693d6d9"
TRANSMOUNTAIN = "https://open.canada.ca/data/en/dataset/dc343c43-a592-4a27-8ee7-c77df56afb34/resource/404fa9e0-73b1-4a8c-9f43-8045d7edb426"

