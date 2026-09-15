"""Result types emitted by source validators."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import StrEnum


class Severity(StrEnum):
    ERROR = "error"
    WARNING = "warning"


@dataclass(frozen=True)
class ValidationIssue:
    rule: str
    message: str
    severity: Severity
    row_number: int | None = None

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass
class ValidationResult:
    source_name: str
    raw_filename: str
    retrieved_at: datetime
    total_rows: int
    passed_rows: int
    rejected_rows: int
    issues: list[ValidationIssue]
    accepted_path: str | None = None
    quarantine_path: str | None = None
    report_path: str | None = None

    @property
    def fatal(self) -> bool:
        return any(issue.row_number is None and issue.severity is Severity.ERROR for issue in self.issues)

    @property
    def warning_count(self) -> int:
        return sum(issue.severity is Severity.WARNING for issue in self.issues)

    @property
    def issue_counts(self) -> dict[str, int]:
        return dict(Counter(issue.rule for issue in self.issues))

    def as_dict(self) -> dict[str, object]:
        return {
            "source_name": self.source_name,
            "raw_filename": self.raw_filename,
            "retrieved_at": self.retrieved_at.isoformat(),
            "total_rows": self.total_rows,
            "passed_rows": self.passed_rows,
            "rejected_rows": self.rejected_rows,
            "warned_rows": self.warning_count,
            "fatal": self.fatal,
            "accepted_path": self.accepted_path,
            "quarantine_path": self.quarantine_path,
            "issues": [issue.as_dict() for issue in self.issues],
            "issue_counts": self.issue_counts,
        }
