from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ValidationIssue:
    severity: str
    code: str
    entity_type: str
    entity_id: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class ValidationResult:
    errors: list[ValidationIssue] = field(default_factory=list)
    warnings: list[ValidationIssue] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not self.errors

    @property
    def status(self) -> str:
        if self.errors:
            return "INVALID"
        if self.warnings:
            return "READY_WITH_WARNINGS"
        return "READY"

    def add_error(self, code: str, entity_type: str, entity_id: str, message: str, **details: Any) -> None:
        self.errors.append(ValidationIssue("ERROR", code, entity_type, entity_id, message, details))

    def add_warning(self, code: str, entity_type: str, entity_id: str, message: str, **details: Any) -> None:
        self.warnings.append(ValidationIssue("WARNING", code, entity_type, entity_id, message, details))
