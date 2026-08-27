from dataclasses import dataclass, field
from enum import Enum


class ValidationSeverity(str, Enum):
    ERROR = "ERROR"
    WARNING = "WARNING"


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    severity: ValidationSeverity
    message: str
    task_ids: tuple[str, ...] = ()
    candidate_ids: tuple[str, ...] = ()
    block_id: str | None = None


@dataclass(frozen=True)
class RepairAction:
    action: str
    candidate_id: str | None
    block_id: str | None
    reason_code: str
    message: str


@dataclass
class ValidationResult:
    valid: bool
    errors: list[ValidationIssue] = field(default_factory=list)
    warnings: list[ValidationIssue] = field(default_factory=list)
    checked_tasks: int = 0
    checked_blocks: int = 0
    repaired: bool = False
    repair_actions: list[RepairAction] = field(default_factory=list)

    @property
    def issues(self) -> list[ValidationIssue]:
        return self.errors + self.warnings
