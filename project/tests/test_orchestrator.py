"""Unit tests for orchestrator task planning without invoking pipeline work."""

from __future__ import annotations

import sys
import unittest
from unittest.mock import patch

from pipeline import orchestrator


class OrchestratorTests(unittest.TestCase):
    def test_dependencies_are_ordered_and_deduplicated(self) -> None:
        plan = orchestrator.resolve_tasks(("transform.pipeline_stage_2",))
        self.assertEqual(
            [task.name for task in plan],
            ["extract.cer", "validate.pipeline", "transform.pipeline_stage_1", "transform.pipeline_stage_2"],
        )

    def test_tm_geo_extract_is_a_standalone_manual_task(self) -> None:
        plan = orchestrator.resolve_tasks(("extract.tm_geo",))
        self.assertEqual([task.name for task in plan], ["extract.tm_geo"])
        self.assertNotIn("extract.tm_geo", orchestrator.TARGETS["extract"])

    def test_validate_stage_includes_report_date_validation_once(self) -> None:
        plan = orchestrator.resolve_tasks(orchestrator.TARGETS["validate"])
        names = [task.name for task in plan]
        self.assertEqual(names.count("extract.cer"), 1)
        self.assertEqual(
            names,
            [
                "extract.cer",
                "validate.pipeline",
                "validate.production",
                "validate.rail",
            ],
        )

    def test_full_stage_validates_all_sources_before_transforming(self) -> None:
        plan = orchestrator.resolve_tasks(orchestrator.TARGETS["full"])
        names = [task.name for task in plan]
        self.assertEqual(
            names,
            [
                "extract.cer",
                "validate.pipeline",
                "validate.production",
                "validate.rail",
                "transform.pipeline_stage_1",
                "transform.pipeline_stage_2",
                "transform.production",
                "transform.rail",
            ],
        )

    def test_transform_stage_validates_all_sources_before_transforming(self) -> None:
        plan = orchestrator.resolve_tasks(orchestrator.TARGETS["transform"])
        names = [task.name for task in plan]
        self.assertEqual(names[:4], [
            "extract.cer",
            "validate.pipeline",
            "validate.production",
            "validate.rail",
        ])

    def test_validation_task_names_match_stage_zero_tasks(self) -> None:
        self.assertEqual(
            orchestrator.VALIDATION_TASK_NAMES,
            {"validate.pipeline", "validate.production", "validate.rail"},
        )

    def test_cycle_is_rejected(self) -> None:
        task = orchestrator.Task
        tasks = {
            "one": task("one", "one", lambda context: None, ("two",)),
            "two": task("two", "two", lambda context: None, ("one",)),
        }
        with patch.dict(orchestrator.TASKS, tasks, clear=True):
            with self.assertRaisesRegex(ValueError, "Cycle detected"):
                orchestrator.resolve_tasks(("one",))

    def test_missing_task_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "not registered"):
            orchestrator.resolve_tasks(("missing.task",))

    def test_no_dependencies_returns_only_requested_task(self) -> None:
        plan = orchestrator.resolve_tasks(("transform.pipeline_stage_2",), include_dependencies=False)
        self.assertEqual([task.name for task in plan], ["transform.pipeline_stage_2"])

    def test_dry_run_does_not_create_a_run_context(self) -> None:
        with (
            patch.object(sys, "argv", ["orchestrator", "validate", "--dry-run"]),
            patch.object(orchestrator.RunContext, "create") as create_context,
        ):
            orchestrator.main()
        create_context.assert_not_called()
