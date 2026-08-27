from dataclasses import dataclass
from datetime import datetime

from app.domain.models import Task
from .config import PriorityConfig
from .scoring import PriorityComponents, calculate_score


@dataclass(frozen=True)
class PriorityResult:
    task_id: str
    score: float
    band: str
    mandatory: bool
    latest_finish: datetime
    components: PriorityComponents


class PriorityEngine:
    def __init__(self, config: PriorityConfig | None = None):
        self.config = config or PriorityConfig()

    def score_task(self, task: Task) -> PriorityResult:
        score, components = calculate_score(task, self.config)
        return PriorityResult(
            task_id=task.task_id,
            score=score,
            band=self.config.band(score),
            mandatory=task.mandatory,
            latest_finish=task.latest_finish,
            components=components,
        )

    def rank(self, tasks: list[Task]) -> list[PriorityResult]:
        results = [self.score_task(task) for task in tasks]
        return sorted(
            results,
            key=lambda result: (
                not result.mandatory,
                -result.score,
                result.latest_finish,
                result.task_id,
            ),
        )
