"""Tests for retrieval-log lineage without HTTP requests."""

from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from pipeline.utils.run_context import RunContext
from pipeline.utils.web_download import record_retrieval


class RetrievalLogTests(unittest.TestCase):
    def test_distinct_run_contexts_receive_distinct_ids(self) -> None:
        first = RunContext.create("forced")
        second = RunContext.create("scheduled")
        self.assertNotEqual(first.run_id, second.run_id)
        self.assertEqual(first.run_type, "forced")
        self.assertEqual(second.run_type, "scheduled")

    def test_forced_and_scheduled_runs_preserve_lineage(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            log = Path(temporary) / "retrieval_log.csv"
            record_retrieval("one", "one.csv", log, "forced-run", "forced")
            record_retrieval("two", "two.csv", log, "forced-run", "forced")
            record_retrieval("three", "three.csv", log, "scheduled-run", "scheduled")
            with log.open(newline="", encoding="utf-8") as file:
                rows = list(csv.DictReader(file))

        self.assertEqual([row["run_id"] for row in rows[:2]], ["forced-run", "forced-run"])
        self.assertEqual([row["run_type"] for row in rows[:2]], ["forced", "forced"])
        self.assertEqual(rows[2]["run_id"], "scheduled-run")
        self.assertEqual(rows[2]["run_type"], "scheduled")
