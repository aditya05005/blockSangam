from dataclasses import dataclass, field
from enum import Enum

from app.candidates.models import Candidate


class ScheduleStatus(str, Enum):
    OPTIMAL = "OPTIMAL"
    FEASIBLE = "FEASIBLE"
    INFEASIBLE = "INFEASIBLE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class ScheduleResult:
    status: ScheduleStatus
    selected_candidates: tuple[Candidate, ...] = ()
    objective_value: float = 0.0
    solve_time_seconds: float = 0.0
    message: str = ""
    unscheduled_mandatory_task_ids: tuple[str, ...] = ()
