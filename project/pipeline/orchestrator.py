"""Command-line orchestrator for the Alberta oil ETL pipeline.

Examples:
    python -m pipeline.orchestrator full
    python -m pipeline.orchestrator extract
    python -m pipeline.orchestrator transform
    python -m pipeline.orchestrator task transform.rail
    python -m pipeline.orchestrator list

Scheduler integration:
    A scheduler should invoke the required stage with ``--run-type scheduled``;
    for example, ``python -m pipeline.orchestrator full --run-type scheduled``.
    Manual invocations default to ``forced``. The orchestrator generates one
    UUID ``run_id`` per invocation and records it with every retrieved source,
    so downstream metadata can be tied to the scheduled or forced refresh.

Selecting a stage runs its upstream dependencies by default.  Use --no-deps
only when the required upstream artifacts already exist and you intentionally
want to skip them.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from pipeline.utils.run_context import RUN_TYPES, RunContext


TaskRunner = Callable[[RunContext], None]
VALIDATION_TASK_NAMES = frozenset(
    {
        "validate.pipeline",
        "validate.production",
        "validate.rail",
    }
)
PIPELINE_TRANSFORM_TASK_NAMES = frozenset(
    {
        "transform.pipeline_stage_1",
        "transform.pipeline_stage_2",
    }
)


@dataclass(frozen=True)
class Task:
    """One executable unit in the pipeline dependency graph."""

    name: str
    description: str
    runner: TaskRunner
    dependencies: tuple[str, ...] = ()


def run_extract_cer(context: RunContext) -> None:
    from pipeline.extract.cer_extract import main

    main(run_id=context.run_id, run_type=context.run_type)


def run_extract_tm_geo(context: RunContext) -> None:
    from pipeline.extract.tm_geo_extract import main

    main(run_id=context.run_id, run_type=context.run_type)


def run_validate_pipeline(context: RunContext) -> None:
    from pipeline.validate.a_0_pipeline_validation import validate_pipeline_throughput
    from pipeline.validate.common import print_validation_result

    for result in validate_pipeline_throughput():
        print_validation_result(result)


def run_validate_production(context: RunContext) -> None:
    from pipeline.validate.b_0_production_validation import validate_production
    from pipeline.validate.common import print_validation_result

    result = validate_production()
    print_validation_result(result)
    if result.fatal:
        raise RuntimeError("Production input validation failed.")


def run_validate_rail(context: RunContext) -> None:
    from pipeline.validate.c_0_rail_validation import validate_rail
    from pipeline.validate.common import print_validation_result

    result = validate_rail()
    print_validation_result(result)
    if result.fatal:
        raise RuntimeError("Rail input validation failed.")


def run_transform_pipeline_stage_1(context: RunContext) -> None:
    from pipeline.transform.a_1_pipeline_transform import main

    main([])


def run_transform_pipeline_stage_2(context: RunContext) -> None:
    from pipeline.transform.a_2_throughput_standardization import main

    main()


def run_transform_production(context: RunContext) -> None:
    from pipeline.transform.b_1_production_transform import main

    main()


def run_transform_rail(context: RunContext) -> None:
    from pipeline.transform.c_1_rail_transform import main

    main()


# Keep orchestrator task names source-based (for example, ``validate.pipeline``)
# to match transform task names. Stage letter/number prefixes belong only in
# validator filenames, where they document source grouping and file order.
TASKS: dict[str, Task] = {
    "extract.cer": Task(
        name="extract.cer",
        description="Download all configured CER source files.",
        runner=run_extract_cer,
    ),
    # Static reference geometry: manually invoke with
    # ``python -m pipeline.orchestrator task extract.tm_geo``.
    "extract.tm_geo": Task(
        name="extract.tm_geo",
        description="Download the one-time NRCan Trans Mountain GeoJSON snapshot.",
        runner=run_extract_tm_geo,
    ),
    "validate.pipeline": Task(
        name="validate.pipeline",
        description="Validate pipeline-throughput inputs and quarantine invalid rows.",
        runner=run_validate_pipeline,
        dependencies=("extract.cer",),
    ),
    "validate.production": Task(
        name="validate.production",
        description="Validate production rows and report-date metadata.",
        runner=run_validate_production,
        dependencies=("extract.cer",),
    ),
    "validate.rail": Task(
        name="validate.rail",
        description="Validate rail rows and report-date metadata.",
        runner=run_validate_rail,
        dependencies=("extract.cer",),
    ),
    "transform.pipeline_stage_1": Task(
        name="transform.pipeline_stage_1",
        description="Create per-pipeline flow and capacity files.",
        runner=run_transform_pipeline_stage_1,
        dependencies=("validate.pipeline",),
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
        dependencies=("validate.production",),
    ),
    "transform.rail": Task(
        name="transform.rail",
        description="Create the monthly rail-export table.",
        runner=run_transform_rail,
        dependencies=("validate.rail",),
    ),
}

# Stage-0 validators are explicitly listed in transform/full targets even though
# downstream transform dependencies also reach them. This documents the
# all-source preflight barrier and keeps it visible in dry-run plans.
TARGETS: dict[str, tuple[str, ...]] = {
    "extract": ("extract.cer",),
    "validate": (
        "validate.pipeline",
        "validate.production",
        "validate.rail",
    ),
    "transform": (
        "validate.pipeline",
        "validate.production",
        "validate.rail",
        "transform.pipeline_stage_2",
        "transform.production",
        "transform.rail",
    ),
    "load": (),
    "full": (
        "validate.pipeline",
        "validate.production",
        "validate.rail",
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
            "--run-type",
            choices=RUN_TYPES,
            default="forced",
            help="Classify this invocation for lineage logging (default: forced).",
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
    task_parser.add_argument("--run-type", choices=RUN_TYPES, default="forced")
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


def run_task(task: Task, context: RunContext) -> None:
    """Run one task with consistent task-level status messages."""
    print(f"\nStarting: {task.name}")
    task.runner(context)
    print(f"Completed: {task.name}")


def run_task_sequence(tasks: list[Task], context: RunContext) -> None:
    """Run a dependency-ordered task branch sequentially."""
    for task in tasks:
        run_task(task, context)


def run_plan(plan: list[Task], context: RunContext) -> None:
    """Run preflight validation, then independent transform branches in parallel."""
    first_validation_index = next(
        (index for index, task in enumerate(plan) if task.name in VALIDATION_TASK_NAMES),
        len(plan),
    )
    prerequisite_tasks = plan[:first_validation_index]
    validation_tasks = [task for task in plan if task.name in VALIDATION_TASK_NAMES]
    downstream_tasks = [
        task for task in plan[first_validation_index:] if task.name not in VALIDATION_TASK_NAMES
    ]
    for task in prerequisite_tasks:
        run_task(task, context)
    if validation_tasks:
        print("\nRunning validation preflight in parallel:")
        with ThreadPoolExecutor(max_workers=len(validation_tasks)) as executor:
            futures = {task.name: executor.submit(run_task, task, context) for task in validation_tasks}
            for task in validation_tasks:
                futures[task.name].result()
    pipeline_tasks = [task for task in downstream_tasks if task.name in PIPELINE_TRANSFORM_TASK_NAMES]
    independent_tasks = [task for task in downstream_tasks if task.name not in PIPELINE_TRANSFORM_TASK_NAMES]
    branch_count = len(independent_tasks) + bool(pipeline_tasks)
    if branch_count <= 1:
        run_task_sequence(pipeline_tasks or independent_tasks, context)
        return

    print("\nRunning transform branches in parallel:")
    with ThreadPoolExecutor(max_workers=branch_count) as executor:
        futures = []
        if pipeline_tasks:
            futures.append(executor.submit(run_task_sequence, pipeline_tasks, context))
        futures.extend(executor.submit(run_task, task, context) for task in independent_tasks)
        for future in futures:
            future.result()


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

    context = RunContext.create(args.run_type)
    print(f"Run: {context.run_id} ({context.run_type})")
    run_plan(plan, context)
    print("\nPipeline run completed successfully.")


if __name__ == "__main__":
    main()
