"""Offline regression tests for rail-workbook validation."""

from __future__ import annotations

import unittest
from unittest.mock import patch

import polars as pl

from pipeline.validate.models import Severity
from pipeline.validate.rail import validate_rail


class RailValidationTests(unittest.TestCase):
    def test_valid_rail_rows_are_accepted_without_network_access(self) -> None:
        rail_frame = pl.DataFrame({"year": [2025], "month": ["January"], "volume_m3_per_day": [12.5]})
        with (
            patch("pipeline.validate.rail.read_rail_sheet", return_value=rail_frame),
            patch(
                "pipeline.validate.rail.source_update_metadata",
                return_value={"report_date": "2025-02-01T00:00:00+00:00"},
            ),
            patch("pipeline.validate.rail.finalize_frame", side_effect=lambda *args: args[4]),
        ):
            issues = validate_rail()
        self.assertFalse(any(issue.severity is Severity.ERROR for issue in issues))
