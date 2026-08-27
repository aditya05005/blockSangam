from datetime import datetime, timedelta

from app.loaders import CanonicalDataset
from app.domain.models import Resource, Task, TrainMovement, CorridorSlot, LockedCommitment
from .compatibility import compatible_task_slot
from .models import Candidate, CandidateGenerationResult, CandidateRejection


class CandidateGenerator:
    def __init__(self, granularity_minutes: int = 30):
        if granularity_minutes <= 0:
            raise ValueError("granularity_minutes must be positive")
        self.granularity = timedelta(minutes=granularity_minutes)

    def generate(self, dataset: CanonicalDataset) -> CandidateGenerationResult:
        result = CandidateGenerationResult()
        candidate_number = 1

        for task in dataset.tasks:
            task_generated = False
            for slot in dataset.corridor_slots:
                compatible, code, message = compatible_task_slot(task, slot)
                if not compatible:
                    result.rejections.append(CandidateRejection(task.task_id, slot.slot_id, code, message))
                    continue

                window_start = max(task.earliest_start, slot.start_time)
                window_end = min(task.latest_finish, slot.end_time)
                duration = timedelta(minutes=task.duration_minutes + task.restoration_minutes)

                start = _ceil_to_granularity(window_start, self.granularity)
                while start + duration <= window_end:
                    end = start + duration
                    reason = self._conflict_reason(task, start, end, dataset)
                    if reason:
                        result.rejections.append(CandidateRejection(task.task_id, slot.slot_id, reason[0], reason[1]))
                    else:
                        resources = _available_resources(task, start, end, dataset.resources)
                        if resources is None:
                            result.rejections.append(CandidateRejection(task.task_id, slot.slot_id, "RESOURCE_UNAVAILABLE", "No compatible resource is available for the candidate interval."))
                        else:
                            result.candidates.append(
                                Candidate(
                                    candidate_id=f"CAND-{candidate_number:04d}",
                                    task_id=task.task_id,
                                    slot_id=slot.slot_id,
                                    start_time=start,
                                    end_time=end,
                                    section=task.section,
                                    line=task.line,
                                    resource_ids=tuple(r.resource_id for r in resources),
                                )
                            )
                            candidate_number += 1
                            task_generated = True
                    start += self.granularity

            if not task_generated and not any(r.task_id == task.task_id and r.reason_code == "NO_FIT_IN_SLOT" for r in result.rejections):
                result.rejections.append(CandidateRejection(task.task_id, "*", "NO_FEASIBLE_CANDIDATE", "No feasible candidate could be generated for this task."))

        return result

    def _conflict_reason(self, task: Task, start: datetime, end: datetime, dataset: CanonicalDataset):
        if task.requires_traffic_block:
            for movement in dataset.movements:
                if _overlaps(task.section, task.line, start, end, movement.section, movement.line, movement.start_time, movement.end_time):
                    return "MOVEMENT_CONFLICT", "Candidate overlaps a train movement on the same section and line."
            for lock in dataset.locked_commitments:
                if lock.locked and _overlaps(task.section, task.line, start, end, lock.section, lock.line, lock.start_time, lock.end_time):
                    return "LOCKED_COMMITMENT_CONFLICT", "Candidate overlaps a locked commitment on the same section and line."
        return None


def _overlaps(section_a, line_a, start_a, end_a, section_b, line_b, start_b, end_b):
    return section_a == section_b and line_a == line_b and start_a < end_b and start_b < end_a


def _available_resources(task: Task, start: datetime, end: datetime, resources: list[Resource]):
    eligible = [r for r in resources if r.department == task.department and r.start_time <= start and r.end_time >= end and r.capacity > 0]
    return eligible[:1] if eligible else None


def _ceil_to_granularity(value: datetime, granularity: timedelta) -> datetime:
    epoch = datetime(1970, 1, 1, tzinfo=value.tzinfo)
    elapsed = value - epoch
    units = (elapsed + granularity - timedelta(microseconds=1)) // granularity
    return epoch + units * granularity
