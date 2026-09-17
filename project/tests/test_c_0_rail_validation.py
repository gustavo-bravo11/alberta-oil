"""Offline regression tests for rail-workbook validation."""

from __future__ import annotations

from pathlib import Path
import unittest
from unittest.mock import patch

import polars as pl

from pipeline.validate.models import Severity
from pipeline.validate.c_0_rail_validation import validate_rail
from pipeline.transform.c_1_rail_transform import source_update_metadata


class RailValidationTests(unittest.TestCase):
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

    def test_valid_rail_rows_are_accepted_without_network_access(self) -> None:
        rail_frame = pl.DataFrame({"year": [2025], "month": ["January"], "volume_m3_per_day": [12.5]})
        with (
            patch("pipeline.validate.c_0_rail_validation.read_rail_sheet", return_value=rail_frame),
            patch(
                "pipeline.validate.c_0_rail_validation.source_update_metadata",
                return_value={"report_date": "2025-02-01T00:00:00+00:00"},
            ),
            patch("pipeline.validate.c_0_rail_validation.finalize_frame", side_effect=lambda *args, **kwargs: args[4]),
        ):
            issues = validate_rail()
        self.assertFalse(any(issue.severity is Severity.ERROR for issue in issues))

    def test_unparseable_report_date_uses_latest_month_end_with_warning(self) -> None:
        rail_frame = pl.DataFrame({"year": [2025], "month": ["July"], "volume_m3_per_day": [12.5]})
        with (
            patch("pipeline.validate.c_0_rail_validation.read_rail_sheet", return_value=rail_frame),
            patch("pipeline.validate.c_0_rail_validation.source_update_metadata", side_effect=ValueError("No update date")),
            patch("pipeline.validate.c_0_rail_validation.finalize_frame", side_effect=lambda *args, **kwargs: args[4]),
            self.assertWarnsRegex(RuntimeWarning, "assuming 2025-07-31"),
        ):
            issues = validate_rail()
        warnings = [issue for issue in issues if issue.rule == "report_date_assumed"]
        self.assertEqual(len(warnings), 1)
        self.assertIs(warnings[0].severity, Severity.WARNING)

    def test_stale_rail_report_date_is_an_error(self) -> None:
        rail_frame = pl.DataFrame({"year": [2025], "month": ["January"], "volume_m3_per_day": [12.5]})
        with (
            patch("pipeline.validate.c_0_rail_validation.read_rail_sheet", return_value=rail_frame),
            patch(
                "pipeline.validate.c_0_rail_validation.source_update_metadata",
                return_value={"report_date": "2024-12-01T00:00:00+00:00"},
            ),
            patch("pipeline.validate.c_0_rail_validation.finalize_frame", side_effect=lambda *args, **kwargs: args[4]),
        ):
            issues = validate_rail()
        self.assertTrue(any(issue.rule == "report_date" and issue.severity is Severity.ERROR for issue in issues))
