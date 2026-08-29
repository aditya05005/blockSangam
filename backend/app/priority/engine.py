from dataclasses import dataclass
from datetime import datetime

from app.domain.models import Task
from app.ml.inference import load_priority_predictor


@dataclass(frozen=True)
class PriorityResult:
    task_id: str
    score: float
    band: str
    mandatory: bool
    latest_finish: datetime
    prediction_source: str
    confidence: float
    factors: tuple[str, ...]
    model_version: str
    ml_score: float


def _risk_band(score: float) -> str:
    if score >= 0.75:
        return "CRITICAL"
    if score >= 0.55:
        return "HIGH"
    if score >= 0.35:
        return "MEDIUM"
    return "LOW"


class PriorityEngine:
    """Authoritative ML priority provider used directly by CP-SAT."""

    def __init__(self):
        # The artifact is required: there is deliberately no rules fallback.
        self.predictor = load_priority_predictor()

    def score_task(self, task: Task) -> PriorityResult:
        prediction = self.predictor.predict(task)
        score = prediction.score
        return PriorityResult(
            task_id=task.task_id,
            score=score,
            band=_risk_band(score),
            mandatory=task.mandatory,
            latest_finish=task.latest_finish,
            prediction_source="ML_MODEL",
            confidence=prediction.confidence,
            factors=prediction.factors,
            model_version=prediction.model_version,
            ml_score=prediction.score,
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
