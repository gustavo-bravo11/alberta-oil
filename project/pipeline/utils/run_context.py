"""Run identity shared by extraction, validation, and transformation."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4


RUN_TYPES = ("forced", "scheduled")


@dataclass(frozen=True)
class RunContext:
    run_id: str
    run_type: str

    @classmethod
    def create(cls, run_type: str = "forced") -> "RunContext":
        if run_type not in RUN_TYPES:
            raise ValueError(f"run_type must be one of: {', '.join(RUN_TYPES)}")
        return cls(run_id=str(uuid4()), run_type=run_type)
