from __future__ import annotations

import hashlib
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from app.blocks.models import BlockPlanningResult, JointBlock
from app.candidates.models import Candidate, CandidateGenerationResult, CandidateRejection
from app.domain.models import CorridorSlot, LockedCommitment, Resource, Task, TrainMovement
from app.loaders import CanonicalDataset
from app.output.serializer import to_dict
from app.priority import PriorityEngine


SOURCE_FILES = {
    "tms": "tms_tasks.csv",
    "smms": "smms_tasks.csv",
    "tdms": "tdms_tasks.csv",
    "timetable": "timetable_movements.csv",
    "corridor_slots": "corridor_slots.csv",
    "resources": "resource_calendar.csv",
    "commitments": "locked_commitments.csv",
}


def _json_models(values) -> list[dict[str, Any]]:
    return [value.model_dump(mode="json") for value in values]


def dataset_to_payload(dataset: CanonicalDataset) -> dict[str, Any]:
    """Convert a canonical dataset into the immutable snapshot payload."""
    return {
        "engineering_tasks": _json_models(dataset.engineering_tasks),
        "snt_tasks": _json_models(dataset.snt_tasks),
        "trd_tasks": _json_models(dataset.trd_tasks),
        "passenger_movements": _json_models(dataset.passenger_movements),
        "goods_movements": _json_models(dataset.goods_movements),
        "corridor_slots": _json_models(dataset.corridor_slots),
        "resources": _json_models(dataset.resources),
        "locked_commitments": _json_models(dataset.locked_commitments),
        "errors": list(dataset.errors),
    }


def dataset_from_payload(payload: dict[str, Any]) -> CanonicalDataset:
    """Rehydrate a snapshot without rereading mutable uploaded files."""
    return CanonicalDataset(
        engineering_tasks=[Task.model_validate(v) for v in payload.get("engineering_tasks", [])],
        snt_tasks=[Task.model_validate(v) for v in payload.get("snt_tasks", [])],
        trd_tasks=[Task.model_validate(v) for v in payload.get("trd_tasks", [])],
        passenger_movements=[TrainMovement.model_validate(v) for v in payload.get("passenger_movements", [])],
        goods_movements=[TrainMovement.model_validate(v) for v in payload.get("goods_movements", [])],
        corridor_slots=[CorridorSlot.model_validate(v) for v in payload.get("corridor_slots", [])],
        resources=[Resource.model_validate(v) for v in payload.get("resources", [])],
        locked_commitments=[LockedCommitment.model_validate(v) for v in payload.get("locked_commitments", [])],
        errors=list(payload.get("errors", [])),
    )


def source_hashes(data_dir: str | Path, goods_forecast: str = "base") -> dict[str, str]:
    data_dir = Path(data_dir)
    files = dict(SOURCE_FILES)
    files["goods_forecast"] = f"goods_forecast_{goods_forecast}.csv"
    result = {}
    for name, filename in files.items():
        path = data_dir / filename
        digest = hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else "missing"
        result[name] = f"sha256:{digest}"
    return result


def build_baseline(dataset: CanonicalDataset, candidates: CandidateGenerationResult) -> tuple[Candidate, ...]:
    """First-feasible-slot, no-global-reconsideration baseline.

    It uses the exact candidate set and hard conflicts as the optimizer. The
    only difference is task ordering and the fact that it never seeks joint
    blocks, making the comparison meaningful.
    """
    priority = {result.task_id: result for result in PriorityEngine().rank(dataset.tasks)}
    ordered = sorted(
        dataset.tasks,
        key=lambda task: (not task.mandatory, task.latest_finish, -priority[task.task_id].score, task.task_id),
    )
    by_task = {task_id: [] for task_id in (task.task_id for task in dataset.tasks)}
    for candidate in candidates.candidates:
        by_task.setdefault(candidate.task_id, []).append(candidate)

    selected: list[Candidate] = []
    for task in ordered:
        for candidate in by_task.get(task.task_id, []):
            if any(_conflicts(candidate, other) for other in selected):
                continue
            selected.append(candidate)
            break
    return tuple(selected)


def _conflicts(left: Candidate, right: Candidate) -> bool:
    overlap = left.start_time < right.end_time and right.start_time < left.end_time
    same_corridor = left.section == right.section and left.line == right.line
    shared_resource = bool(set(left.resource_ids) & set(right.resource_ids))
    return overlap and (same_corridor or shared_resource)


def explain_unscheduled(dataset: CanonicalDataset, candidates: CandidateGenerationResult, selected: tuple[Candidate, ...]) -> list[dict[str, Any]]:
    selected_tasks = {candidate.task_id for candidate in selected}
    rejected_by_task: dict[str, list[CandidateRejection]] = {}
    for rejection in candidates.rejections:
        rejected_by_task.setdefault(rejection.task_id, []).append(rejection)
    output = []
    priority = {result.task_id: result for result in PriorityEngine().rank(dataset.tasks)}
    for task in dataset.tasks:
        if task.task_id in selected_tasks:
            continue
        rejections = rejected_by_task.get(task.task_id, [])
        has_candidates = any(candidate.task_id == task.task_id for candidate in candidates.candidates)
        meaningful = [r for r in rejections if r.reason_code not in {"SECTION_MISMATCH", "LINE_MISMATCH"}]
        if meaningful:
            counts = Counter(r.reason_code for r in meaningful)
            reason = counts.most_common(1)[0][0]
            representative = next(r for r in meaningful if r.reason_code == reason)
        else:
            reason = "OPTIMIZER_NOT_SELECTED" if has_candidates else "NO_COMPATIBLE_SLOT"
            representative = None
        output.append(
            {
                "task_id": task.task_id,
                "department": task.department.value,
                "criticality": task.criticality,
                "due_date": task.latest_finish.isoformat(),
                "priority": {
                    "score": priority[task.task_id].score,
                    "band": priority[task.task_id].band,
                    "source": priority[task.task_id].prediction_source,
                    "confidence": priority[task.task_id].confidence,
                    "factors": list(priority[task.task_id].factors),
                    "model_version": priority[task.task_id].model_version,
                },
                "status": "UNSCHEDULED",
                "reason_code": reason,
                "candidate_state": "CANDIDATES_EXISTED" if has_candidates else "NO_CANDIDATES_GENERATED",
                "candidate_count": sum(candidate.task_id == task.task_id for candidate in candidates.candidates),
                "explanation": representative.message if representative else "No feasible assignment survived the planning constraints.",
                "conflicting_slot": representative.slot_id if representative else None,
            }
        )
    return output


def calculate_metrics(dataset: CanonicalDataset, blocks: BlockPlanningResult, selected: tuple[Candidate, ...], solver_runtime_seconds: float, *, previous_selected: tuple[Candidate, ...] = (), hard_constraint_violations: int = 0) -> dict[str, float]:
    task_map = {task.task_id: task for task in dataset.tasks}
    mandatory = [task for task in dataset.tasks if task.mandatory]
    mandatory_scheduled = sum(task.task_id in {c.task_id for c in selected} for task in mandatory)
    block_minutes = sum(_minutes(block.start_time, block.end_time) for block in blocks.joint_blocks)
    traffic = sum(_minutes(block.start_time, block.end_time) for block in blocks.joint_blocks if block.traffic_block or any(task_map[c.task_id].requires_traffic_block for c in selected if c.candidate_id in block.candidate_ids))
    power = sum(_minutes(block.start_time, block.end_time) for block in blocks.joint_blocks if block.power_isolation or any(task_map[c.task_id].requires_power_isolation for c in selected if c.candidate_id in block.candidate_ids))
    snt = sum(_minutes(block.start_time, block.end_time) for block in blocks.joint_blocks if block.snt_disconnection or any(task_map[c.task_id].requires_snt_disconnection for c in selected if c.candidate_id in block.candidate_ids))
    train_impact = sum(
        1
        for candidate in selected
        for movement in dataset.movements
        if candidate.section == movement.section
        and candidate.line == movement.line
        and candidate.start_time < movement.end_time
        and movement.start_time < candidate.end_time
    )
    departments_per_block = [len({task_map[c.task_id].department.value for c in selected if c.candidate_id in block.candidate_ids}) for block in blocks.joint_blocks]
    task_count = len(selected)
    resource_minutes: dict[str, float] = Counter()
    for candidate in selected:
        for resource_id in candidate.resource_ids:
            resource_minutes[resource_id] += _minutes(candidate.start_time, candidate.end_time)
    horizon_start = min((task.earliest_start for task in dataset.tasks), default=None)
    horizon_end = max((task.latest_finish for task in dataset.tasks), default=None)
    horizon_minutes = _minutes(horizon_start, horizon_end) if horizon_start and horizon_end else 0
    available_minutes = sum(_minutes(resource.start_time, resource.end_time) for resource in dataset.resources)
    unavailable_minutes = sum(
        max(0, horizon_minutes - _minutes(max(horizon_start, resource.start_time), min(horizon_end, resource.end_time)))
        if horizon_start and horizon_end else 0
        for resource in dataset.resources
    )
    used_minutes = sum(resource_minutes.values())
    previous_map = {c.task_id: (c.start_time, c.end_time) for c in previous_selected}
    unchanged = sum(c.task_id in previous_map and previous_map[c.task_id] == (c.start_time, c.end_time) for c in selected)
    stability = (100.0 * unchanged / len(previous_map)) if previous_map else 100.0
    weighted_overdue = sum(
        PriorityEngine().score_task(task).score for task in dataset.tasks if task.task_id not in {c.task_id for c in selected} and task.latest_finish < max((c.end_time for c in selected), default=task.latest_finish)
    )
    return {
        "hard_constraint_violations": float(hard_constraint_violations),
        "mandatory_tasks_scheduled": float(mandatory_scheduled),
        "mandatory_tasks_missed": float(len(mandatory) - mandatory_scheduled),
        "weighted_overdue_exposure": round(weighted_overdue, 6),
        "tasks_scheduled": float(task_count),
        "tasks_unscheduled": float(len(dataset.tasks) - task_count),
        "traffic_block_minutes": float(traffic),
        "power_block_minutes": float(power),
        "snt_disconnection_minutes": float(snt),
        "train_impact_proxy": float(train_impact),
        "asset_unavailable_minutes": float(unavailable_minutes),
        "tasks_per_block": round(task_count / len(blocks.joint_blocks), 6) if blocks.joint_blocks else 0.0,
        "joint_blocks_created": float(len(blocks.joint_blocks)),
        "mobilizations_avoided": float(sum(max(0, count - 1) for count in departments_per_block)),
        "unused_block_minutes": float(max(0, block_minutes - sum(_minutes(c.start_time, c.end_time) for c in selected))),
        "resource_utilization": round(100.0 * used_minutes / available_minutes, 6) if available_minutes else 0.0,
        "plan_stability_percentage": round(stability, 6),
        "solver_runtime_seconds": round(solver_runtime_seconds, 6),
    }


def _minutes(start: datetime, end: datetime) -> int:
    return int((end - start).total_seconds() // 60)


def build_plan_payload(result, dataset: CanonicalDataset, unscheduled: list[dict[str, Any]], metrics: dict[str, float], *, baseline_selected: tuple[Candidate, ...] = (), baseline_metrics: dict[str, float] | None = None) -> dict[str, Any]:
    payload = to_dict(result)
    payload["schedule"] = {
        "status": result.schedule.status.value,
        "message": result.schedule.message,
        "objective_value": result.schedule.objective_value,
        "solve_time_seconds": result.schedule.solve_time_seconds,
    }
    payload["tasks"] = [task.model_dump(mode="json") for task in dataset.tasks]
    payload["locked_blocks"] = [
        {
            "commitment_id": commitment.commitment_id,
            "section": commitment.section,
            "line": commitment.line.value,
            "start_time": commitment.start_time.isoformat(),
            "end_time": commitment.end_time.isoformat(),
            "block_type": commitment.block_type.value,
            "description": commitment.description,
            "locked": commitment.locked,
        }
        for commitment in dataset.locked_commitments
    ]
    payload["unscheduled"] = unscheduled
    payload["metrics"] = metrics
    payload["baseline"] = {
        "selected_task_ids": [candidate.task_id for candidate in baseline_selected],
        "tasks_scheduled": len(baseline_selected),
        "metrics": baseline_metrics or {},
    }
    payload["selected_candidates"] = [
        {
            "candidate_id": candidate.candidate_id,
            "task_id": candidate.task_id,
            "slot_id": candidate.slot_id,
            "start_time": candidate.start_time.isoformat(),
            "end_time": candidate.end_time.isoformat(),
            "section": candidate.section,
            "line": candidate.line.value,
            "resource_ids": list(candidate.resource_ids),
        }
        for candidate in result.schedule.selected_candidates
    ]
    return payload
