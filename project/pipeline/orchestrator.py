"""Command-line orchestrator for the Alberta oil ETL pipeline.

Examples:
    python -m pipeline.orchestrator full
    python -m pipeline.orchestrator extract
    python -m pipeline.orchestrator transform
    python -m pipeline.orchestrator task transform.rail
    python -m pipeline.orchestrator list

Selecting a stage runs its upstream dependencies by default.  Use --no-deps
only when the required upstream artifacts already exist and you intentionally
want to skip them.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Iterable
from dataclasses import dataclass


TaskRunner = Callable[[], None]


@dataclass(frozen=True)
class Task:
    """One executable unit in the pipeline dependency graph."""

    name: str
    description: str
    runner: TaskRunner
    dependencies: tuple[str, ...] = ()


def run_extract_cer() -> None:
    from pipeline.extract.cer_extract import main

    main()


def run_transform_pipeline_stage_1() -> None:
    from pipeline.transform.a_1_pipeline_transform import main

    main([])


def run_transform_pipeline_stage_2() -> None:
    from pipeline.transform.a_2_throughput_standardization import main

    main()


def run_transform_production() -> None:
    from pipeline.transform.b_1_production_transform import main

    main()


def run_transform_rail() -> None:
    from pipeline.transform.c_1_rail_transform import main

    main()


TASKS: dict[str, Task] = {
    "extract.cer": Task(
        name="extract.cer",
        description="Download all configured CER source files.",
        runner=run_extract_cer,
    ),
    "transform.pipeline_stage_1": Task(
        name="transform.pipeline_stage_1",
        description="Create per-pipeline flow and capacity files.",
        runner=run_transform_pipeline_stage_1,
        dependencies=("extract.cer",),
    ),
    "transform.pipeline_stage_2": Task(
        name="transform.pipeline_stage_2",
        description="Standardize the consolidated pipeline flow and capacity files.",
        runner=run_transform_pipeline_stage_2,
        dependencies=("transform.pipeline_stage_1",),
    ),
    "transform.production": Task(
        name="transform.production",
        description="Create the Alberta and Saskatchewan production table.",
        runner=run_transform_production,
        dependencies=("extract.cer",),
    ),
    "transform.rail": Task(
        name="transform.rail",
        description="Create the monthly rail-export table.",
        runner=run_transform_rail,
        dependencies=("extract.cer",),
    ),
}

TARGETS: dict[str, tuple[str, ...]] = {
    "extract": ("extract.cer",),
    "transform": (
        "transform.pipeline_stage_2",
        "transform.production",
        "transform.rail",
    ),
    "load": (),
    "full": (
        "transform.pipeline_stage_2",
        "transform.production",
        "transform.rail",
    ),
}


def resolve_tasks(targets: Iterable[str], include_dependencies: bool = True) -> list[Task]:
    """Return selected tasks in dependency-safe order and reject invalid DAGs."""
    ordered: list[Task] = []
    visited: set[str] = set()
    visiting: set[str] = set()

    def visit(task_name: str) -> None:
        if task_name in visited:
            return
        if task_name in visiting:
            raise ValueError(f"Cycle detected in task graph at '{task_name}'.")
        try:
            task = TASKS[task_name]
        except KeyError as error:
            raise ValueError(f"Task '{task_name}' is not registered.") from error

        visiting.add(task_name)
        if include_dependencies:
            for dependency in task.dependencies:
                visit(dependency)
        visiting.remove(task_name)
        visited.add(task_name)
        ordered.append(task)

    for target in targets:
        visit(target)
    return ordered


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    for command in TARGETS:
        command_parser = subparsers.add_parser(command, help=f"Run the {command} stage.")
        command_parser.add_argument(
            "--no-deps",
            action="store_true",
            help="Do not run upstream dependencies.",
        )
        command_parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print the resolved execution plan without running it.",
        )

    task_parser = subparsers.add_parser("task", help="Run one granular task by name.")
    task_parser.add_argument("name", choices=sorted(TASKS))
    task_parser.add_argument("--no-deps", action="store_true", help="Do not run upstream dependencies.")
    task_parser.add_argument("--dry-run", action="store_true", help="Print the plan without running it.")
    subparsers.add_parser("list", help="List stages and granular tasks.")
    return parser


def list_tasks() -> None:
    print("Stages:")
    for name, task_names in TARGETS.items():
        members = ", ".join(task_names) if task_names else "(no tasks registered yet)"
        print(f"  {name}: {members}")
    print("\nTasks:")
    for task in TASKS.values():
        dependencies = ", ".join(task.dependencies) or "none"
        print(f"  {task.name}\n    {task.description}\n    depends on: {dependencies}")


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "list":
        list_tasks()
        return

    task_names = (args.name,) if args.command == "task" else TARGETS[args.command]
    plan = resolve_tasks(task_names, include_dependencies=not args.no_deps)
    if not plan:
        print("No load tasks are registered yet. Add a Task to TASKS when the load layer exists.")
        return

    print("Execution plan:")
    for index, task in enumerate(plan, start=1):
        print(f"  {index}. {task.name}")
    if args.dry_run:
        return

    for task in plan:
        print(f"\nRunning: {task.name}")
        task.runner()
    print("\nPipeline run completed successfully.")


if __name__ == "__main__":
    main()
