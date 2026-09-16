"""Offline regression tests for production-workbook validation."""

from __future__ import annotations

import unittest
from unittest.mock import patch

import polars as pl

from pipeline.validate.models import Severity
from pipeline.validate.production import PRODUCTION_COLUMNS, PRODUCTION_COMPONENTS, validate_production


class WorkbookInputValidationTests(unittest.TestCase):
    def production_frame(self, canada_total: float) -> pl.DataFrame:
        row = {column: 0.0 for column in PRODUCTION_COLUMNS}
        row["month"] = "Jan-25"
        for column in PRODUCTION_COMPONENTS:
            row[column] = 1.0
        row["canada_total"] = canada_total
        return pl.DataFrame([row])

    def production_issues(self, canada_total: float):
        with (
            patch("pipeline.validate.production.pl.read_excel", return_value=self.production_frame(canada_total)),
            patch(
                "pipeline.validate.production.production_report_metadata",
                return_value={"report_date": "2025-02-01T00:00:00+00:00", "latest_data_month": "2025-01-01"},
            ),
            patch("pipeline.validate.production.finalize_frame", side_effect=lambda *args: args[4]),
        ):
            return validate_production()

    def test_production_components_reconcile_without_warning(self) -> None:
        issues = self.production_issues(float(len(PRODUCTION_COMPONENTS)))
        self.assertFalse(any(issue.rule == "canada_total_reconciliation" for issue in issues))

    def test_production_reconciliation_mismatch_is_warning(self) -> None:
        issues = self.production_issues(999.0)
        warnings = [issue for issue in issues if issue.rule == "canada_total_reconciliation"]
        self.assertEqual(len(warnings), 1)
        self.assertIs(warnings[0].severity, Severity.WARNING)
