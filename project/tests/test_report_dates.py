"""Tests for deterministic production-sheet selection and rail date parsing."""

from __future__ import annotations

from datetime import date
from pathlib import Path
import unittest
from unittest.mock import patch

import polars as pl

from pipeline.transform.c_1_rail_transform import source_update_metadata
from pipeline.utils.workbook_metadata import select_production_report_sheet
from pipeline.validate.report_dates import validate_report_dates


class ReportDateTests(unittest.TestCase):
    def test_current_year_production_sheet_is_selected(self) -> None:
        selected = select_production_report_sheet(
            {"26TABLE - cubic meters per day", "25TABLE - cubic meters per day"}, date(2026, 9, 16)
        )
        self.assertEqual(selected, "26TABLE - cubic meters per day")

    def test_prior_year_production_sheet_is_fallback(self) -> None:
        selected = select_production_report_sheet({"25TABLE - cubic meters per day"}, date(2026, 9, 16))
        self.assertEqual(selected, "25TABLE - cubic meters per day")

    def test_missing_current_and_prior_production_sheets_fails(self) -> None:
        with self.assertRaisesRegex(ValueError, "Neither the current nor prior"):
            select_production_report_sheet({"24TABLE - cubic meters per day"}, date(2026, 9, 16))

    def rail_metadata(self, label: str) -> dict[str, str]:
        with patch(
            "pipeline.transform.c_1_rail_transform.read_rail_sheet",
            return_value=pl.DataFrame([[label]]),
        ):
            return source_update_metadata(Path("rail.xlsx"))

    def test_rail_report_date_variations_are_parsed(self) -> None:
        labels = (
            "Numbers last updated on September 10, 2026",
            "  Numbers last updated: September 10, 2026  ",
            "Last updated September 10th, 2026",
            "Data current as of September 10, 2026",
        )
        for label in labels:
            with self.subTest(label=label):
                metadata = self.rail_metadata(label)
                self.assertEqual(metadata["report_date"], "2026-09-10T00:00:00+00:00")

    def test_rail_report_date_without_parseable_date_fails(self) -> None:
        with self.assertRaisesRegex(ValueError, "No 'Last updated' value found"):
            self.rail_metadata("Last updated sometime soon")

    def test_report_date_validator_accepts_current_metadata(self) -> None:
        rail_rows = pl.DataFrame({"year": [2025], "month": ["January"]})
        with (
            patch(
                "pipeline.validate.report_dates.production_report_metadata",
                return_value={"report_date": "2025-02-01T00:00:00+00:00", "latest_data_month": "2025-01-01"},
            ),
            patch("pipeline.validate.report_dates.read_rail_sheet", return_value=rail_rows),
            patch(
                "pipeline.validate.report_dates.source_update_metadata",
                return_value={"report_date": "2025-02-01T00:00:00+00:00"},
            ),
        ):
            validate_report_dates()

    def test_report_date_validator_rejects_stale_rail_metadata(self) -> None:
        rail_rows = pl.DataFrame({"year": [2025], "month": ["January"]})
        with (
            patch(
                "pipeline.validate.report_dates.production_report_metadata",
                return_value={"report_date": "2025-02-01T00:00:00+00:00", "latest_data_month": "2025-01-01"},
            ),
            patch("pipeline.validate.report_dates.read_rail_sheet", return_value=rail_rows),
            patch(
                "pipeline.validate.report_dates.source_update_metadata",
                return_value={"report_date": "2024-12-01T00:00:00+00:00"},
            ),
        ):
            with self.assertRaisesRegex(ValueError, "earlier than the latest rail-data month"):
                validate_report_dates()

    def test_report_date_validator_assumes_latest_month_end_when_label_is_missing(self) -> None:
        rail_rows = pl.DataFrame({"year": [2025], "month": ["July"]})
        with (
            patch(
                "pipeline.validate.report_dates.production_report_metadata",
                return_value={"report_date": "2025-08-01T00:00:00+00:00", "latest_data_month": "2025-07-01"},
            ),
            patch("pipeline.validate.report_dates.read_rail_sheet", return_value=rail_rows),
            patch("pipeline.validate.report_dates.source_update_metadata", side_effect=ValueError("No update date")),
            self.assertWarnsRegex(RuntimeWarning, "assuming 2025-07-31"),
        ):
            validate_report_dates()
