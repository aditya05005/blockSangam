from collections import Counter
from datetime import datetime
from typing import Iterable

from app.domain.models import CorridorSlot, LockedCommitment, Resource, Task, TrainMovement
from .result import ValidationResult

VALID_SECTIONS = {
    "Thane-Kurla", "Kurla-Chembur", "Chembur-Mankhurd",
    "CSMT-Dadar", "Dadar-Kurla", "Ghatkopar-Vikhroli", "Mankhurd-Vashi",
    # Retained for unit fixtures and backwards-compatible persisted snapshots.
    "A-B", "B-C", "C-D",
}


def _timezone_aware(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() is not None


def validate_tasks(tasks: Iterable[Task], result: ValidationResult) -> None:
    tasks = list(tasks)
    ids = [t.task_id for t in tasks]
    for task_id, count in Counter(ids).items():
        if count > 1:
            result.add_error("DUPLICATE_ID", "Task", task_id, "Task ID occurs more than once.", count=count)
    for task in tasks:
        if task.section not in VALID_SECTIONS:
            result.add_error("INVALID_SECTION", "Task", task.task_id, "Unknown corridor section.", section=task.section)
        if not _timezone_aware(task.earliest_start) or not _timezone_aware(task.latest_finish):
            result.add_error("NAIVE_TIMESTAMP", "Task", task.task_id, "Task timestamps must include a timezone.")
        window_minutes = (task.latest_finish - task.earliest_start).total_seconds() / 60
        required_minutes = task.duration_minutes + task.restoration_minutes
        if required_minutes > window_minutes:
            result.add_error("WINDOW_TOO_SHORT", "Task", task.task_id, "Task duration plus restoration does not fit its declared window.", window_minutes=window_minutes, required_minutes=required_minutes)
        if task.mandatory and task.duration_minutes > 0 and window_minutes < task.duration_minutes:
            result.add_warning("TIGHT_WINDOW", "Task", task.task_id, "Mandatory task has a tight feasible window.")


def validate_movements(movements: Iterable[TrainMovement], result: ValidationResult) -> None:
    movements = list(movements)
    ids = [m.movement_id for m in movements]
    for movement_id, count in Counter(ids).items():
        if count > 1:
            result.add_error("DUPLICATE_ID", "TrainMovement", movement_id, "Movement ID occurs more than once.", count=count)
    for movement in movements:
        if movement.section not in VALID_SECTIONS:
            result.add_error("INVALID_SECTION", "TrainMovement", movement.movement_id, "Unknown corridor section.", section=movement.section)
        if not _timezone_aware(movement.start_time) or not _timezone_aware(movement.end_time):
            result.add_error("NAIVE_TIMESTAMP", "TrainMovement", movement.movement_id, "Movement timestamps must include a timezone.")


def validate_slots(slots: Iterable[CorridorSlot], result: ValidationResult) -> None:
    slots = list(slots)
    ids = [s.slot_id for s in slots]
    for slot_id, count in Counter(ids).items():
        if count > 1:
            result.add_error("DUPLICATE_ID", "CorridorSlot", slot_id, "Slot ID occurs more than once.", count=count)
    for slot in slots:
        if slot.section not in VALID_SECTIONS:
            result.add_error("INVALID_SECTION", "CorridorSlot", slot.slot_id, "Unknown corridor section.", section=slot.section)
        if not all(_timezone_aware(x) for x in (slot.start_time, slot.end_time)):
            result.add_error("NAIVE_TIMESTAMP", "CorridorSlot", slot.slot_id, "Slot timestamps must include a timezone.")


def validate_resources(resources: Iterable[Resource], result: ValidationResult) -> None:
    resources = list(resources)
    ids = [r.resource_id for r in resources]
    for resource_id, count in Counter(ids).items():
        if count > 1:
            result.add_error("DUPLICATE_ID", "Resource", resource_id, "Resource ID occurs more than once.", count=count)
    for resource in resources:
        if not all(_timezone_aware(x) for x in (resource.start_time, resource.end_time)):
            result.add_error("NAIVE_TIMESTAMP", "Resource", resource.resource_id, "Resource calendar timestamps must include a timezone.")


def validate_commitments(commitments: Iterable[LockedCommitment], result: ValidationResult) -> None:
    commitments = list(commitments)
    ids = [c.commitment_id for c in commitments]
    for commitment_id, count in Counter(ids).items():
        if count > 1:
            result.add_error("DUPLICATE_ID", "LockedCommitment", commitment_id, "Commitment ID occurs more than once.", count=count)
    for commitment in commitments:
        if commitment.section not in VALID_SECTIONS:
            result.add_error("INVALID_SECTION", "LockedCommitment", commitment.commitment_id, "Unknown corridor section.", section=commitment.section)
        if not all(_timezone_aware(x) for x in (commitment.start_time, commitment.end_time)):
            result.add_error("NAIVE_TIMESTAMP", "LockedCommitment", commitment.commitment_id, "Commitment timestamps must include a timezone.")
