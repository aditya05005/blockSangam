from dataclasses import dataclass

from app.domain.models import Task
from .config import PriorityConfig


@dataclass(frozen=True)
class PriorityComponents:
    criticality: float
    defect_severity: float
    asset_criticality: float
    failure_consequence: float
    deferral_history: float
    mandatory_bonus: float

    @property
    def total(self) -> float:
        return (
            self.criticality
            + self.defect_severity
            + self.asset_criticality
            + self.failure_consequence
            + self.deferral_history
            + self.mandatory_bonus
        )


def normalize_five(value: int) -> float:
    return (value - 1) / 4.0


def normalize_deferral(value: int, cap: int) -> float:
    return min(value / cap, 1.0)


def calculate_components(task: Task, config: PriorityConfig) -> PriorityComponents:
    return PriorityComponents(
        criticality=normalize_five(task.criticality) * config.criticality_weight,
        defect_severity=normalize_five(task.defect_severity) * config.defect_severity_weight,
        asset_criticality=normalize_five(task.asset_criticality) * config.asset_criticality_weight,
        failure_consequence=normalize_five(task.failure_consequence) * config.failure_consequence_weight,
        deferral_history=normalize_deferral(task.deferral_history, config.deferral_cap) * config.deferral_history_weight,
        mandatory_bonus=config.mandatory_bonus if task.mandatory else 0.0,
    )


def calculate_score(task: Task, config: PriorityConfig) -> tuple[float, PriorityComponents]:
    components = calculate_components(task, config)
    return round(min(components.total, 1.0), 6), components
