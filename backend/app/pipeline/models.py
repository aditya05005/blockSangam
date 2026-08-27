from dataclasses import dataclass, field

from app.blocks.models import BlockPlanningResult
from app.validation.models import ValidationResult
from app.scheduler.models import ScheduleResult


@dataclass(frozen=True)
class PipelineStatistics:
    tasks_considered: int
    tasks_scheduled: int
    candidates_generated: int
    candidates_selected: int
    joint_blocks: int
    total_time_seconds: float


@dataclass
class PipelineResult:
    status: str
    schedule: ScheduleResult
    blocks: BlockPlanningResult
    validation: ValidationResult
    statistics: PipelineStatistics
    input_errors: list[dict] = field(default_factory=list)
