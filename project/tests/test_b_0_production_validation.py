"""Offline regression tests for production-workbook validation."""

from __future__ import annotations

from datetime import date
import unittest
from unittest.mock import patch

import polars as pl

from pipeline.validate.models import Severity
from pipeline.utils.workbook_metadata import select_production_report_sheet
from pipeline.validate.b_0_production_validation import PRODUCTION_COLUMNS, PRODUCTION_COMPONENTS, validate_production


class ProductionValidationTests(unittest.TestCase):
    def production_frame(self, canada_total: float) -> pl.DataFrame:
        row = {column: 0.0 for column in PRODUCTION_COLUMNS}
        row["month"] = "Jan-25"
        for column in PRODUCTION_COMPONENTS:
            row[column] = 1.0
        row["canada_total"] = canada_total
        return pl.DataFrame([row])

    def production_issues(self, canada_total: float, report_date: str = "2025-02-01T00:00:00+00:00"):
        with (
            patch("pipeline.validate.b_0_production_validation.pl.read_excel", return_value=self.production_frame(canada_total)),
            patch(
                "pipeline.validate.b_0_production_validation.production_report_metadata",
                return_value={"report_date": report_date, "latest_data_month": "2025-01-01"},
            ),
            patch("pipeline.validate.b_0_production_validation.finalize_frame", side_effect=lambda *args: args[4]),
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

    def test_stale_production_report_date_is_an_error(self) -> None:
        issues = self.production_issues(float(len(PRODUCTION_COMPONENTS)), "2024-12-01T00:00:00+00:00")
        self.assertTrue(any(issue.rule == "report_date" and issue.severity is Severity.ERROR for issue in issues))

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
