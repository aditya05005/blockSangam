from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from app.candidates import CandidateGenerator
from app.loaders import CanonicalDataset, load_dataset
from app.pipeline import BlockSangamPipeline, PipelineResult
from app.planning import dataset_from_payload, dataset_to_payload, explain_unscheduled
from app.priority import PriorityEngine
from app.domain.models import BlockType, Department, Line, LockedCommitment, Task

from .scenarios import materialize_scenario, scenario_definition


@dataclass(frozen=True)
class ScenarioExecution:
    scenario_id: str
    definition: Any
    dataset: CanonicalDataset
    candidates: Any
    result: PipelineResult


@dataclass(frozen=True)
class RuntimeScenarioDefinition:
    label: str
    description: str
    forecast: str
    modifications: tuple[str, ...]


def execute_scenario(scenario_id: str, base_dir: str | Path, *, max_solve_time_seconds: float = 10.0) -> ScenarioExecution:
    """Execute a scenario from an isolated filesystem copy.

    The returned domain objects are in memory; the temporary copy is deleted
    after loading, so neither the base files nor a later run can be affected.
    """
    definition = scenario_definition(scenario_id)
    base_dir = Path(base_dir)
    with TemporaryDirectory(prefix=f"blocksangam-{scenario_id}-") as temporary:
        scenario_dir = materialize_scenario(scenario_id, Path(temporary) / "data", base_dir)
        dataset = load_dataset(scenario_dir, goods_forecast=definition.forecast)
    if dataset.errors:
        raise ValueError(f"Input dataset contains {len(dataset.errors)} error(s)")
    candidates = CandidateGenerator().generate(dataset)
    result = BlockSangamPipeline(max_solve_time_seconds=max_solve_time_seconds).run_dataset(dataset)
    return ScenarioExecution(scenario_id, definition, dataset, candidates, result)


def scenario_options(base_dir: str | Path) -> dict[str, list[dict[str, str]]]:
    """Selectable identifiers from the base snapshot, not frontend constants."""
    dataset = load_dataset(base_dir)
    corridors = sorted({(slot.section, slot.line.value) for slot in dataset.corridor_slots})
    return {
        "corridor_slots": [{"id": slot.slot_id, "label": f"{slot.slot_id} — {slot.section} {slot.line.value}"} for slot in dataset.corridor_slots],
        "resources": [{"id": item.resource_id, "label": f"{item.resource_name} ({item.resource_id})"} for item in dataset.resources],
        "corridors": [{"section": section, "line": line, "label": f"{section} {line}"} for section, line in corridors],
    }


def _india_time(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone(timedelta(hours=5, minutes=30)))


def execute_custom_scenario(changes: dict[str, Any], base_dir: str | Path, *, max_solve_time_seconds: float = 10.0) -> ScenarioExecution:
    """Apply user changes to an in-memory clone; the base snapshot stays untouched."""
    forecast = changes.get("goods_forecast", "base")
    base = load_dataset(base_dir, goods_forecast=forecast)
    if base.errors:
        raise ValueError(f"Input dataset contains {len(base.errors)} error(s)")
    dataset = dataset_from_payload(dataset_to_payload(base))
    notes: list[str] = []

    slot_ids = set(changes.get("remove_corridor_slot_ids", []))
    unknown_slots = sorted(slot_ids - {slot.slot_id for slot in dataset.corridor_slots})
    if unknown_slots:
        raise ValueError(f"Unknown corridor slot(s): {', '.join(unknown_slots)}")
    dataset.corridor_slots = [slot for slot in dataset.corridor_slots if slot.slot_id not in slot_ids]
    notes.extend(f"remove corridor slot {slot_id}" for slot_id in sorted(slot_ids))

    resource_ids = set(changes.get("unavailable_resource_ids", []))
    unknown_resources = sorted(resource_ids - {item.resource_id for item in dataset.resources})
    if unknown_resources:
        raise ValueError(f"Unknown resource(s): {', '.join(unknown_resources)}")
    dataset.resources = [item for item in dataset.resources if item.resource_id not in resource_ids]
    notes.extend(f"make resource unavailable: {resource_id}" for resource_id in sorted(resource_ids))

    closure = changes.get("corridor_closure")
    if closure:
        section, line = closure["section"], Line(closure["line"])
        if not any(slot.section == section and slot.line == line for slot in base.corridor_slots):
            raise ValueError(f"Unknown corridor: {section} {line.value}")
        start, end = _india_time(closure["start_time"]), _india_time(closure["end_time"])
        dataset.locked_commitments.append(LockedCommitment(
            commitment_id=f"SCN-CLOSURE-{len(dataset.locked_commitments) + 1:03d}", section=section, line=line,
            start_time=start, end_time=end, block_type=BlockType.FULL_BLOCK,
            description="User what-if corridor closure", locked=True,
        ))
        notes.append(f"block corridor {section} {line.value} from {start.isoformat()} to {end.isoformat()}")

    task_input = changes.get("add_optional_task")
    if task_input:
        task_id = task_input["task_id"].strip()
        if any(task.task_id == task_id for task in dataset.tasks):
            raise ValueError(f"Task ID already exists: {task_id}")
        section, line = task_input["section"], Line(task_input["line"])
        if not any(slot.section == section and slot.line == line for slot in base.corridor_slots):
            raise ValueError(f"Unknown corridor: {section} {line.value}")
        task = Task(
            task_id=task_id, department=Department(task_input["department"]), section=section, line=line,
            task_type=task_input["task_type"], duration_minutes=task_input["duration_minutes"],
            earliest_start=_india_time(task_input["earliest_start"]), latest_finish=_india_time(task_input["latest_finish"]),
            criticality=task_input.get("criticality", 3), defect_severity=task_input.get("defect_severity", 3),
            asset_criticality=task_input.get("asset_criticality", 3), failure_consequence=task_input.get("failure_consequence", 3),
            deferral_history=0, mandatory=False, requires_traffic_block=True,
            requires_power_isolation=task_input.get("requires_power_isolation", False),
            requires_snt_disconnection=task_input.get("requires_snt_disconnection", False),
        )
        if task.department is Department.ENGINEERING:
            dataset.engineering_tasks.append(task)
        elif task.department is Department.SNT:
            dataset.snt_tasks.append(task)
        else:
            dataset.trd_tasks.append(task)
        notes.append(f"add optional maintenance task {task_id}")

    if forecast != "base":
        notes.append(f"use {forecast} goods forecast")
    definition = RuntimeScenarioDefinition("Custom what-if", "User-configured planning experiment.", forecast, tuple(notes or ("none",)))
    candidates = CandidateGenerator().generate(dataset)
    result = BlockSangamPipeline(max_solve_time_seconds=max_solve_time_seconds).run_dataset(dataset)
    return ScenarioExecution("custom", definition, dataset, candidates, result)


def mandatory_scheduled(execution: ScenarioExecution) -> int:
    mandatory = {task.task_id for task in execution.dataset.tasks if task.mandatory}
    return sum(candidate.task_id in mandatory for candidate in execution.result.schedule.selected_candidates)


def execution_payload(execution: ScenarioExecution) -> dict[str, Any]:
    result = execution.result
    selected = tuple(result.schedule.selected_candidates)
    task_map = {task.task_id: task for task in execution.dataset.tasks}
    entries = []
    priorities = {item.task_id: item for item in PriorityEngine().rank(execution.dataset.tasks)}
    for candidate in selected:
        task = task_map[candidate.task_id]
        priority = priorities[task.task_id]
        entries.append({
            "candidate_id": candidate.candidate_id, "task_id": candidate.task_id,
            "department": task.department.value, "section": candidate.section,
            "line": candidate.line.value, "task_type": task.task_type,
            "start_time": candidate.start_time.isoformat(), "end_time": candidate.end_time.isoformat(),
            "resource_ids": list(candidate.resource_ids), "slot_id": candidate.slot_id,
            "mandatory": task.mandatory, "duration_minutes": task.duration_minutes + task.restoration_minutes,
            "latest_finish": task.latest_finish.isoformat(), "priority": priority.score,
            "priority_band": priority.band, "requires_traffic_block": task.requires_traffic_block,
            "requires_power_isolation": task.requires_power_isolation,
            "requires_snt_disconnection": task.requires_snt_disconnection,
        })
    blocks = [
        {"block_id": block.block_id, "section": block.section, "line": block.line.value,
         "start_time": block.start_time.isoformat(), "end_time": block.end_time.isoformat(),
         "task_ids": list(block.task_ids), "candidate_ids": list(block.candidate_ids)}
        for block in result.blocks.joint_blocks
    ]
    return {
        "scenario": {
            "id": execution.scenario_id, "name": execution.definition.label,
            "description": execution.definition.description,
            "forecast": execution.definition.forecast,
            "modifications": list(execution.definition.modifications),
        },
        "status": result.status,
        "validation_status": "VALID" if result.validation.valid else "INVALID",
        "summary": {
            "tasks_considered": result.statistics.tasks_considered,
            "tasks_scheduled": result.statistics.tasks_scheduled,
            "mandatory_tasks_scheduled": mandatory_scheduled(execution),
            "candidates_generated": result.statistics.candidates_generated,
            "candidates_selected": result.statistics.candidates_selected,
            "joint_blocks": result.statistics.joint_blocks,
            "total_time_seconds": result.statistics.total_time_seconds,
        },
        "solver": {
            "status": result.schedule.status.value, "message": result.schedule.message,
            "objective_value": result.schedule.objective_value,
            "solve_time_seconds": result.schedule.solve_time_seconds,
            "unscheduled_mandatory_task_ids": list(result.schedule.unscheduled_mandatory_task_ids),
        },
        "schedule_entries": entries,
        "blocks": blocks,
        "unscheduled": explain_unscheduled(execution.dataset, execution.candidates, selected),
        "validation": {"valid": result.validation.valid,
                        "errors": [asdict(issue) for issue in result.validation.errors],
                        "warnings": [asdict(issue) for issue in result.validation.warnings]},
        "advisory": "SIH prototype - advisory only; not an operational Indian Railways block grant.",
    }


def compare_executions(base: ScenarioExecution, scenario: ScenarioExecution) -> dict[str, Any]:
    def assignments(execution):
        return {candidate.task_id: candidate for candidate in execution.result.schedule.selected_candidates}

    base_map, scenario_map = assignments(base), assignments(scenario)
    newly_unscheduled = sorted(set(base_map) - set(scenario_map))
    newly_scheduled = sorted(set(scenario_map) - set(base_map))
    moved = sorted(
        task_id for task_id in set(base_map) & set(scenario_map)
        if (base_map[task_id].start_time, base_map[task_id].end_time, base_map[task_id].slot_id)
        != (scenario_map[task_id].start_time, scenario_map[task_id].end_time, scenario_map[task_id].slot_id)
    )
    base_status = base.result.status
    scenario_status = scenario.result.status
    return {
        "base": {"status": base_status, "validation_status": "VALID" if base.result.validation.valid else "INVALID",
                 "tasks_scheduled": base.result.statistics.tasks_scheduled, "candidates_generated": base.result.statistics.candidates_generated,
                 "joint_blocks": base.result.statistics.joint_blocks, "objective_value": base.result.schedule.objective_value},
        "scenario": {"status": scenario_status, "validation_status": "VALID" if scenario.result.validation.valid else "INVALID",
                      "tasks_scheduled": scenario.result.statistics.tasks_scheduled, "candidates_generated": scenario.result.statistics.candidates_generated,
                      "joint_blocks": scenario.result.statistics.joint_blocks, "objective_value": scenario.result.schedule.objective_value},
        "impact": {
            "status_changed": base_status != scenario_status,
            "newly_unscheduled": newly_unscheduled,
            "newly_scheduled": newly_scheduled,
            "tasks_moved": moved,
            "candidate_delta": scenario.result.statistics.candidates_generated - base.result.statistics.candidates_generated,
            "joint_block_delta": scenario.result.statistics.joint_blocks - base.result.statistics.joint_blocks,
            "objective_delta": scenario.result.schedule.objective_value - base.result.schedule.objective_value,
            "validation_changed": base.result.validation.valid != scenario.result.validation.valid,
        },
    }


def simulate_scenario(scenario_id: str, base_dir: str | Path, *, max_solve_time_seconds: float = 10.0) -> dict[str, Any]:
    base = execute_scenario("base", base_dir, max_solve_time_seconds=max_solve_time_seconds)
    scenario = execute_scenario(scenario_id, base_dir, max_solve_time_seconds=max_solve_time_seconds)
    return {"base": execution_payload(base), "scenario_result": execution_payload(scenario), "comparison": compare_executions(base, scenario)}


def simulate_custom_scenario(changes: dict[str, Any], base_dir: str | Path, *, max_solve_time_seconds: float = 10.0) -> dict[str, Any]:
    base = execute_scenario("base", base_dir, max_solve_time_seconds=max_solve_time_seconds)
    scenario = execute_custom_scenario(changes, base_dir, max_solve_time_seconds=max_solve_time_seconds)
    return {"base": execution_payload(base), "scenario_result": execution_payload(scenario), "comparison": compare_executions(base, scenario)}
