"""Regression tests for raw pipeline-throughput validation."""

from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from pipeline.validate.contracts import CONTRACTS
from pipeline.validate.raw_throughput import validate_file


class RawThroughputValidationTests(unittest.TestCase):
    contract = CONTRACTS["enbridge_mainline"]

    def write_source(self, directory: Path, rows: list[dict[str, str]]) -> Path:
        path = directory / self.contract.raw_filename
        with path.open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=self.contract.required_columns)
            writer.writeheader()
            writer.writerows(rows)
        return path

    def valid_row(self) -> dict[str, str]:
        return {
            "Date": "2026-08-01",
            "Month": "8",
            "Year": "2026",
            "Company": "Enbridge Pipelines Inc.",
            "Pipeline": "Enbridge Canadian Mainline system",
            "Key Point": "Into-Sarnia",
            "Latitude": "42.953",
            "Longitude": "-82.372",
            "Direction Of Flow": "east",
            "Trade Type": "import",
            "Product": "foreign light",
            "Throughput (1000 m3/d)": "3.8",
            "Nameplate Capacity (1000 m3/d)": "123.1",
            "Available Capacity (1000 m3/d)": "118.5",
            "Reason For Variance": "",
        }

    def validate(self, rows: list[dict[str, str]]):
        temporary = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        return validate_file(
            self.contract,
            self.write_source(root, rows),
            root / "validated",
            root / "quarantine",
            root / "reports",
        )

    def test_valid_product_row_is_accepted(self) -> None:
        result = self.validate([self.valid_row()])
        self.assertFalse(result.fatal)
        self.assertEqual(result.passed_rows, 1)
        self.assertEqual(result.rejected_rows, 0)
        self.assertTrue(Path(result.accepted_path or "").exists())

    def test_unapproved_product_is_quarantined(self) -> None:
        row = self.valid_row()
        row["Product"] = "unapproved product"
        result = self.validate([row])
        self.assertFalse(result.fatal)
        self.assertEqual(result.passed_rows, 0)
        self.assertEqual(result.rejected_rows, 1)
        self.assertTrue(Path(result.quarantine_path or "").exists())

    def test_helper_row_is_exempt_from_field_validation(self) -> None:
        row = self.valid_row()
        row.update(
            {
                "Key Point": "system",
                "Latitude": "",
                "Longitude": "",
                "Direction Of Flow": "",
                "Trade Type": "",
                "Product": "",
                "Throughput (1000 m3/d)": "",
                "Nameplate Capacity (1000 m3/d)": "",
                "Available Capacity (1000 m3/d)": "",
            }
        )
        result = self.validate([row])
        self.assertEqual(result.passed_rows, 1)
        self.assertEqual(result.rejected_rows, 0)

    def test_duplicate_normalized_key_quarantines_both_rows(self) -> None:
        first = self.valid_row()
        second = self.valid_row()
        second["Pipeline"] = "Enbridge Canadian Mainline system\n"
        result = self.validate([first, second])
        self.assertEqual(result.passed_rows, 0)
        self.assertEqual(result.rejected_rows, 2)


if __name__ == "__main__":
    unittest.main()
