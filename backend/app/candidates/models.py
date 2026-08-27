from dataclasses import dataclass, field
from datetime import datetime

from app.domain.models import Line


@dataclass(frozen=True)
class Candidate:
    candidate_id: str
    task_id: str
    slot_id: str
    start_time: datetime
    end_time: datetime
    section: str
    line: Line
    resource_ids: tuple[str, ...]


@dataclass(frozen=True)
class CandidateRejection:
    task_id: str
    slot_id: str
    reason_code: str
    message: str


@dataclass
class CandidateGenerationResult:
    candidates: list[Candidate] = field(default_factory=list)
    rejections: list[CandidateRejection] = field(default_factory=list)

    @property
    def unschedulable_task_ids(self) -> list[str]:
        candidate_task_ids = {c.task_id for c in self.candidates}
        rejected_task_ids = {r.task_id for r in self.rejections}
        return sorted(rejected_task_ids - candidate_task_ids)
