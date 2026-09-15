"""Read report metadata from CER production workbooks without Excel dependencies."""

from __future__ import annotations

import re
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from xml.etree import ElementTree


MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PACKAGE_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
NAMESPACES = {"m": MAIN, "pr": PACKAGE_REL}
DATE_FORMATS = ("%Y-%m-%d", "%Y/%m/%d", "%B %d, %Y", "%b %d, %Y", "%d %B %Y", "%d %b %Y")
DATE_PATTERNS = (r"\d{4}[-/]\d{1,2}[-/]\d{1,2}", r"[A-Za-z]+\s+\d{1,2},?\s+\d{4}")


def parse_report_date(value: str) -> str:
    """Parse a visible workbook date into an ISO-8601 UTC timestamp."""
    text = value.strip()
    try:
        parsed = datetime(1899, 12, 30) + timedelta(days=float(text))
    except ValueError:
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            for candidate in (text, *(match.group(0) for pattern in DATE_PATTERNS if (match := re.search(pattern, text)))):
                for date_format in DATE_FORMATS:
                    try:
                        parsed = datetime.strptime(candidate, date_format)
                        break
                    except ValueError:
                        continue
                else:
                    continue
                break
            else:
                raise ValueError(f"Could not parse report date: {value!r}")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


class ProductionWorkbook:
    def __init__(self, path: Path):
        self.archive = zipfile.ZipFile(path)
        self.shared_strings = self._shared_strings()
        self.workbook = ElementTree.fromstring(self.archive.read("xl/workbook.xml"))
        self.relationships = ElementTree.fromstring(self.archive.read("xl/_rels/workbook.xml.rels"))

    def close(self) -> None:
        self.archive.close()

    def _shared_strings(self) -> list[str]:
        try:
            document = ElementTree.fromstring(self.archive.read("xl/sharedStrings.xml"))
        except KeyError:
            return []
        return ["".join(item.itertext()) for item in document.findall("m:si", NAMESPACES)]

    def sheet_names(self) -> set[str]:
        return {sheet.attrib["name"] for sheet in self.workbook.findall(".//m:sheet", NAMESPACES)}

    def sheet(self, name: str) -> ElementTree.Element:
        sheet = next((item for item in self.workbook.findall(".//m:sheet", NAMESPACES) if item.attrib["name"] == name), None)
        if sheet is None:
            raise ValueError(f"Worksheet not found: {name}")
        relationship_id = sheet.attrib[f"{{{REL}}}id"]
        relationship = next(item for item in self.relationships.findall("pr:Relationship", NAMESPACES) if item.attrib["Id"] == relationship_id)
        target = relationship.attrib["Target"].lstrip("/")
        if not target.startswith("xl/"):
            target = f"xl/{target}"
        return ElementTree.fromstring(self.archive.read(target))

    def cell_value(self, worksheet: ElementTree.Element, reference: str) -> str:
        cell = next((item for item in worksheet.findall(".//m:c", NAMESPACES) if item.attrib.get("r") == reference), None)
        if cell is None:
            return ""
        value = cell.find("m:v", NAMESPACES)
        raw = "" if value is None or value.text is None else value.text
        if cell.attrib.get("t") == "s" and raw:
            return self.shared_strings[int(raw)]
        return raw

    def column_values(self, worksheet: ElementTree.Element, column: str) -> list[str]:
        values: list[str] = []
        for row in worksheet.findall(".//m:sheetData/m:row", NAMESPACES):
            cell = next(
                (item for item in row.findall("m:c", NAMESPACES) if item.attrib.get("r", "").startswith(column)),
                None,
            )
            if cell is not None:
                reference = cell.attrib["r"]
                if reference[len(column):].isdigit():
                    values.append(self.cell_value(worksheet, reference))
        return values


def excel_date(value: str) -> date:
    try:
        return (datetime(1899, 12, 30) + timedelta(days=float(value))).date()
    except ValueError:
        return datetime.strptime(value, "%b-%y").date()


def production_report_metadata(workbook_path: Path, today: date | None = None) -> dict[str, str]:
    """Select the current-year table, falling back once, and parse its A2 date."""
    reference_date = today or date.today()
    candidate_sheets = (
        f"{reference_date.year % 100:02d}TABLE - cubic meters per day",
        f"{(reference_date.year - 1) % 100:02d}TABLE - cubic meters per day",
    )
    workbook = ProductionWorkbook(workbook_path)
    try:
        selected = next((sheet for sheet in candidate_sheets if sheet in workbook.sheet_names()), None)
        if selected is None:
            raise ValueError("Neither the current nor prior annual production worksheet is available.")
        report_label = workbook.cell_value(workbook.sheet(selected), "A2")
        if not report_label:
            raise ValueError(f"Report date is missing from {selected}!A2.")
        report_date = parse_report_date(report_label)
        history = workbook.sheet("HIST - cubic meters per day")
        months: list[date] = []
        for row in history.findall(".//m:sheetData/m:row", NAMESPACES):
            row_number = row.attrib.get("r")
            if not row_number or row_number == "1":
                continue
            month_value = workbook.cell_value(history, f"A{row_number}")
            has_reported_production = any(
                workbook.cell_value(history, f"{column}{row_number}")
                for column in "BCDEFGHIJKLMNOPQRS"
            )
            if month_value and has_reported_production:
                months.append(excel_date(month_value))
        if not months:
            raise ValueError("No historical production months found.")
        latest_month = max(months)
    finally:
        workbook.close()
    if datetime.fromisoformat(report_date).date() < latest_month:
        raise ValueError("Production report date is earlier than the latest historical production month.")
    return {
        "report_date": report_date,
        "report_label": report_label,
        "report_sheet": selected,
        "latest_data_month": latest_month.isoformat(),
    }
