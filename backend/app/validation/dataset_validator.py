from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.loaders import CanonicalDataset
from .result import ValidationIssue, ValidationResult
from .rules import (
    validate_commitments,
    validate_movements,
    validate_resources,
    validate_slots,
    validate_tasks,
)


@dataclass(frozen=True)
class DatasetSnapshot:
    snapshot_id: str
    created_at: datetime
    goods_forecast: str
    validation_status: str
    error_count: int
    warning_count: int
    source_counts: dict[str, int]


def validate_dataset(dataset: CanonicalDataset) -> ValidationResult:
    result = ValidationResult()

    # Preserve adapter errors as validation errors instead of allowing malformed
    # source rows to silently enter the planning pipeline.
    for error in dataset.errors:
        result.add_error(
            "ADAPTER_ERROR",
            str(error.get("source", "Unknown")),
            str(error.get("row", "unknown")),
            str(error.get("error", "Source adapter rejected row.")),
        )

    validate_tasks(dataset.tasks, result)
    validate_movements(dataset.movements, result)
    validate_slots(dataset.corridor_slots, result)
    validate_resources(dataset.resources, result)
    validate_commitments(dataset.locked_commitments, result)

    _validate_cross_references(dataset, result)
    _validate_overlaps(dataset, result)
    return result


def _validate_cross_references(dataset: CanonicalDataset, result: ValidationResult) -> None:
    slot_keys = {(s.section, s.line) for s in dataset.corridor_slots}
    for task in dataset.tasks:
        if task.requires_traffic_block and (task.section, task.line) not in slot_keys:
            result.add_error("NO_CORRIDOR_SLOT", "Task", task.task_id, "No corridor slot exists on the task's section and line.")

    resource_ids = {r.resource_id for r in dataset.resources}
    if not resource_ids:
        result.add_error("NO_RESOURCES", "Dataset", "resources", "No resources are available for planning.")


def _validate_overlaps(dataset: CanonicalDataset, result: ValidationResult) -> None:
    # Locked commitments may overlap each other only if they refer to different
    # section/line pairs. Overlap on the same physical corridor is contradictory.
    locks = dataset.locked_commitments
    for i, left in enumerate(locks):
        for right in locks[i + 1:]:
            if left.section != right.section or left.line != right.line:
                continue
            if left.start_time < right.end_time and right.start_time < left.end_time:
                result.add_error(
                    "OVERLAPPING_LOCKS",
                    "LockedCommitment",
                    left.commitment_id,
                    "Locked commitments overlap on the same section and line.",
                    conflicting_id=right.commitment_id,
                )


def create_snapshot(dataset: CanonicalDataset, result: ValidationResult, snapshot_id: str, goods_forecast: str = "base") -> DatasetSnapshot:
    if not result.valid:
        raise ValueError("Cannot create a planning snapshot from an invalid dataset")

    return DatasetSnapshot(
        snapshot_id=snapshot_id,
        created_at=datetime.now(timezone.utc),
        goods_forecast=goods_forecast,
        validation_status=result.status,
        error_count=len(result.errors),
        warning_count=len(result.warnings),
        source_counts={
            "engineering_tasks": len(dataset.engineering_tasks),
            "snt_tasks": len(dataset.snt_tasks),
            "trd_tasks": len(dataset.trd_tasks),
            "passenger_movements": len(dataset.passenger_movements),
            "goods_movements": len(dataset.goods_movements),
            "corridor_slots": len(dataset.corridor_slots),
            "resources": len(dataset.resources),
            "locked_commitments": len(dataset.locked_commitments),
        },
    )
