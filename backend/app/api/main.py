from __future__ import annotations

import csv
import io
import tempfile
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy.orm import sessionmaker

from app.candidates import CandidateGenerator
from app.database.models import (
    DataSnapshot,
    ExistingCommitment,
    ImportErrorRecord,
    MaintenanceTask,
    PlanEvent,
    PlanMetric,
    PlanRun,
    PlanStatus,
    ProposedBlock,
    ResourceCalendar,
    SourceRecord,
    TrainMovement,
    UnscheduledTask,
    WorkPackage,
    CorridorSlot,
)
from app.database.session import create_database
from app.loaders import load_dataset
from app.pipeline import BlockSangamPipeline
from app.priority import PriorityEngine
from app.scenarios import available_scenarios, materialize_scenario, scenario_definition
from app.planning import (
    build_baseline,
    build_plan_payload,
    calculate_metrics,
    dataset_from_payload,
    dataset_to_payload,
    explain_unscheduled,
    source_hashes,
)
from app.validation import validate_dataset
from app.blocks.models import BlockPlanningResult


class ImportRequest(BaseModel):
    data_dir: str | None = None
    forecast: str = Field(default="base", min_length=1, max_length=30)


class SnapshotRequest(ImportRequest):
    pass


class PlanRunRequest(BaseModel):
    snapshot_id: str
    planning_mode: Literal["weekly", "monthly"] = "weekly"
    max_solve_time: float = Field(default=10.0, gt=0, le=300)


class ScheduleRequest(BaseModel):
    """Direct, stateless scheduling request for the dashboard."""

    data_dir: str | None = None
    goods_forecast: str = Field(default="base", min_length=1, max_length=30)
    scenario: str = Field(default="base", min_length=1, max_length=40)
    # ``forecast`` is a friendly alias used by simple API clients.
    forecast: str | None = Field(default=None, min_length=1, max_length=30)
    max_solve_time: float = Field(default=10.0, gt=0, le=300)


class ReplanRequest(BaseModel):
    forecast: str = Field(default="stressed", min_length=1, max_length=30)
    planning_mode: Literal["weekly", "monthly"] | None = None
    max_solve_time: float = Field(default=10.0, gt=0, le=300)


class StatusRequest(BaseModel):
    status: PlanStatus


def _default_data_dir() -> str:
    return str(Path(__file__).resolve().parents[3] / "data" / "synthetic")


def _errors(result) -> list[dict]:
    return [
        {
            "severity": issue.severity,
            "code": issue.code,
            "entity_type": issue.entity_type,
            "entity_id": issue.entity_id,
            "message": issue.message,
            "details": issue.details,
        }
        for issue in result.errors
    ]


def _warnings(result) -> list[dict]:
    return [
        {
            "severity": issue.severity,
            "code": issue.code,
            "entity_type": issue.entity_type,
            "entity_id": issue.entity_id,
            "message": issue.message,
            "details": issue.details,
        }
        for issue in result.warnings
    ]


def _schedule_issues(result) -> dict[str, list[dict]]:
    return {
        "errors": [asdict(issue) for issue in result.validation.errors],
        "warnings": [asdict(issue) for issue in result.validation.warnings],
    }


def _schedule_response(result, dataset, *, scenario: str = "base") -> dict:
    priorities = {item.task_id: item for item in PriorityEngine().rank(dataset.tasks)}
    task_map = {task.task_id: task for task in dataset.tasks}
    entries = []
    for candidate in result.schedule.selected_candidates:
        task = task_map[candidate.task_id]
        priority = priorities[task.task_id]
        entries.append(
            {
                "candidate_id": candidate.candidate_id,
                "task_id": task.task_id,
                "department": task.department.value,
                "section": task.section,
                "line": task.line.value,
                "task_type": task.task_type,
                "start_time": candidate.start_time.isoformat(),
                "end_time": candidate.end_time.isoformat(),
                "duration_minutes": task.duration_minutes + task.restoration_minutes,
                "mandatory": task.mandatory,
                "requires_traffic_block": task.requires_traffic_block,
                "requires_power_isolation": task.requires_power_isolation,
                "requires_snt_disconnection": task.requires_snt_disconnection,
                "latest_finish": task.latest_finish.isoformat(),
                "priority": priority.score,
                "priority_band": priority.band,
                "resource_ids": list(candidate.resource_ids),
                "slot_id": candidate.slot_id,
            }
        )
    return {
        "status": result.status,
        "scenario": scenario,
        "validation_status": "VALID" if result.validation.valid else "INVALID",
        "summary": {
            "tasks_considered": result.statistics.tasks_considered,
            "tasks_scheduled": result.statistics.tasks_scheduled,
            "candidates_generated": result.statistics.candidates_generated,
            "candidates_selected": result.statistics.candidates_selected,
            "joint_blocks": result.statistics.joint_blocks,
        },
        "solver": {
            "status": result.schedule.status.value,
            "message": result.schedule.message,
            "objective_value": result.schedule.objective_value,
            "solve_time_seconds": result.schedule.solve_time_seconds,
            "unscheduled_mandatory_task_ids": list(result.schedule.unscheduled_mandatory_task_ids),
        },
        "schedule_entries": entries,
        "unscheduled": explain_unscheduled(dataset, CandidateGenerator().generate(dataset), tuple(result.schedule.selected_candidates)),
        "blocks": [
            {
                "block_id": block.block_id,
                "section": block.section,
                "line": block.line.value,
                "start_time": block.start_time.isoformat(),
                "end_time": block.end_time.isoformat(),
                "task_ids": list(block.task_ids),
                "candidate_ids": list(block.candidate_ids),
            }
            for block in result.blocks.joint_blocks
        ],
        "validation": _schedule_issues(result),
        "advisory": "SIH prototype — advisory only; not an operational Indian Railways block grant.",
    }


def _snapshot_response(snapshot: DataSnapshot, *, errors=None, warnings=None) -> dict:
    return {
        "snapshot_id": snapshot.snapshot_id,
        "schema_version": snapshot.schema_version,
        "created_at": snapshot.created_at.isoformat(),
        "goods_forecast": snapshot.goods_forecast,
        "source_counts": snapshot.source_counts,
        "source_hashes": snapshot.source_hashes,
        "validation_status": snapshot.validation_status,
        "error_count": snapshot.error_count,
        "warning_count": snapshot.warning_count,
        "errors": errors or [],
        "warnings": warnings or [],
        "advisory": "SIH prototype — advisory only; not an operational Indian Railways block grant.",
    }


def _new_snapshot(session, dataset, data_dir: str, forecast: str, validation) -> DataSnapshot:
    snapshot_id = f"SNAP-{datetime.now(timezone.utc):%Y%m%d%H%M%S}-{uuid.uuid4().hex[:6].upper()}"
    payload = dataset_to_payload(dataset)
    source_counts = {
        "engineering_tasks": len(dataset.engineering_tasks),
        "snt_tasks": len(dataset.snt_tasks),
        "trd_tasks": len(dataset.trd_tasks),
        "passenger_movements": len(dataset.passenger_movements),
        "goods_movements": len(dataset.goods_movements),
        "corridor_slots": len(dataset.corridor_slots),
        "resources": len(dataset.resources),
        "locked_commitments": len(dataset.locked_commitments),
    }
    snapshot = DataSnapshot(
        snapshot_id=snapshot_id,
        goods_forecast=forecast,
        data_dir=str(Path(data_dir).resolve()),
        validation_status=validation.status,
        error_count=len(validation.errors),
        warning_count=len(validation.warnings),
        source_counts=source_counts,
        source_hashes=source_hashes(data_dir, forecast),
        payload=payload,
    )
    session.add(snapshot)
    for source_name, values in (
        ("maintenance_tasks", dataset.tasks),
        ("train_movements", dataset.movements),
        ("corridor_slots", dataset.corridor_slots),
        ("resources", dataset.resources),
        ("existing_commitments", dataset.locked_commitments),
    ):
        for value in values:
            record_id = getattr(value, "task_id", None) or getattr(value, "movement_id", None) or getattr(value, "slot_id", None) or getattr(value, "resource_id", None) or getattr(value, "commitment_id", None)
            session.add(SourceRecord(snapshot_id=snapshot_id, source_name=source_name, source_record_id=record_id, payload=value.model_dump(mode="json")))
    for model, values in (
        (MaintenanceTask, dataset.tasks),
        (TrainMovement, dataset.movements),
        (CorridorSlot, dataset.corridor_slots),
        (ResourceCalendar, dataset.resources),
        (ExistingCommitment, dataset.locked_commitments),
    ):
        for value in values:
            session.add(model(snapshot_id=snapshot_id, payload=value.model_dump(mode="json")))
    for issue in validation.errors:
        session.add(ImportErrorRecord(snapshot_id=snapshot_id, source_name=issue.entity_type, row_reference=issue.entity_id, reason_code=issue.code, message=issue.message))
    return snapshot


def _get_snapshot(session, snapshot_id: str) -> DataSnapshot:
    snapshot = session.get(DataSnapshot, snapshot_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail=f"Snapshot {snapshot_id} was not found.")
    return snapshot


def _persist_plan(session, snapshot: DataSnapshot, mode: str, max_solve_time: float, *, previous_plan: PlanRun | None = None) -> PlanRun:
    dataset = dataset_from_payload(snapshot.payload)
    candidates = CandidateGenerator().generate(dataset)
    result = BlockSangamPipeline(max_solve_time_seconds=max_solve_time).run_dataset(dataset)
    selected = tuple(result.schedule.selected_candidates)
    baseline_selected = build_baseline(dataset, candidates)
    unscheduled = explain_unscheduled(dataset, candidates, selected)
    metrics = calculate_metrics(dataset, result.blocks, selected, result.schedule.solve_time_seconds, previous_selected=_selected_from_payload(previous_plan.payload if previous_plan else {}), hard_constraint_violations=len(result.validation.errors))
    baseline_metrics = calculate_metrics(dataset, BlockPlanningResult(), baseline_selected, 0.0)
    payload = build_plan_payload(result, dataset, unscheduled, metrics, baseline_selected=baseline_selected, baseline_metrics=baseline_metrics)
    plan_id = f"{mode.upper()}-{datetime.now(timezone.utc):%Y%m%d%H%M%S}-{uuid.uuid4().hex[:6].upper()}"
    plan = PlanRun(
        plan_id=plan_id,
        snapshot_id=snapshot.snapshot_id,
        planning_mode=mode,
        solver_status=result.schedule.status.value,
        status=PlanStatus.PROPOSED,
        configuration={"max_solve_time_seconds": max_solve_time, "resolution_minutes": 30},
        source_hashes=snapshot.source_hashes,
        payload=payload,
    )
    session.add(plan)
    for block in result.blocks.joint_blocks:
        session.add(ProposedBlock(plan_id=plan_id, external_block_id=block.block_id, payload={"block_id": block.block_id, "section": block.section, "line": block.line.value, "start_time": block.start_time.isoformat(), "end_time": block.end_time.isoformat(), "candidate_ids": list(block.candidate_ids), "task_ids": list(block.task_ids)}))
        for task_id in block.task_ids:
            session.add(WorkPackage(plan_id=plan_id, task_id=task_id, block_id=block.block_id, payload={"task_id": task_id, "block_id": block.block_id}))
    for item in unscheduled:
        session.add(UnscheduledTask(plan_id=plan_id, task_id=item["task_id"], reason_code=item["reason_code"], payload=item))
    for name, value in metrics.items():
        session.add(PlanMetric(plan_id=plan_id, metric_name=name, metric_value=value))
    for name, value in baseline_metrics.items():
        session.add(PlanMetric(plan_id=plan_id, metric_name=f"baseline_{name}", metric_value=value))
    session.add(PlanEvent(plan_id=plan_id, event_type="PLAN_CREATED", details={"snapshot_id": snapshot.snapshot_id, "solver_status": result.schedule.status.value}))
    return plan


def _selected_from_payload(payload: dict) -> tuple:
    # Stability only needs identity and interval; keeping this parser local
    # avoids making database records part of the scheduler domain model.
    from app.candidates.models import Candidate
    from app.domain.models import Line

    return tuple(
        Candidate(
            item["candidate_id"], item["task_id"], item["slot_id"], datetime.fromisoformat(item["start_time"]), datetime.fromisoformat(item["end_time"]), item["section"], Line(item["line"]), tuple(item.get("resource_ids", []))
        )
        for item in payload.get("selected_candidates", [])
    )


def _plan_response(plan: PlanRun) -> dict:
    return {
        "plan_id": plan.plan_id,
        "snapshot_id": plan.snapshot_id,
        "planning_mode": plan.planning_mode,
        "status": plan.status.value,
        "solver_status": plan.solver_status,
        "created_at": plan.created_at.isoformat(),
        "plan": plan.payload,
        "advisory": "SIH prototype — advisory only; not an operational Indian Railways block grant.",
    }


def create_app(database_url: str | None = None) -> FastAPI:
    app = FastAPI(title="BlockSangam internal planning API", version="10.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
        allow_headers=["*"],
    )
    engine = create_database(database_url or "sqlite:///./block_sangam.db")
    app.state.engine = engine
    app.state.sessions = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    @app.get("/api/health")
    def health():
        return {"status": "ok", "service": "BlockSangam", "advisory_only": True}

    @app.get("/api/scenarios")
    def scenarios():
        return {"scenarios": available_scenarios()}

    @app.post("/api/schedule")
    def schedule(request: ScheduleRequest = ScheduleRequest()):
        data_dir = request.data_dir or _default_data_dir()
        try:
            definition = scenario_definition(request.scenario)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        forecast = request.forecast or (definition.forecast if request.scenario != "base" else request.goods_forecast)
        try:
            if request.scenario == "base":
                dataset = load_dataset(data_dir, goods_forecast=forecast)
                result = BlockSangamPipeline(max_solve_time_seconds=request.max_solve_time).run_dataset(dataset)
            else:
                with tempfile.TemporaryDirectory(prefix="blocksangam-scenario-") as temporary:
                    scenario_dir = materialize_scenario(request.scenario, Path(temporary) / "data", data_dir)
                    dataset = load_dataset(scenario_dir, goods_forecast=forecast)
                    result = BlockSangamPipeline(max_solve_time_seconds=request.max_solve_time).run_dataset(dataset)
            if dataset.errors:
                raise HTTPException(status_code=422, detail={"message": "Input dataset contains adapter errors.", "errors": dataset.errors})
        except HTTPException:
            raise
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return _schedule_response(result, dataset, scenario=request.scenario)

    @app.post("/api/imports/validate")
    def validate_import(request: ImportRequest = ImportRequest()):
        data_dir = request.data_dir or _default_data_dir()
        try:
            dataset = load_dataset(data_dir, goods_forecast=request.forecast)
            validation = validate_dataset(dataset)
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {"valid": validation.valid, "status": validation.status, "source_counts": {"tasks": len(dataset.tasks), "movements": len(dataset.movements), "slots": len(dataset.corridor_slots), "resources": len(dataset.resources), "locked_commitments": len(dataset.locked_commitments)}, "errors": _errors(validation), "warnings": _warnings(validation), "advisory": "MOCK/SYNTHETIC data — advisory only."}

    @app.post("/api/snapshots", status_code=201)
    def create_snapshot(request: SnapshotRequest = SnapshotRequest()):
        data_dir = request.data_dir or _default_data_dir()
        try:
            dataset = load_dataset(data_dir, goods_forecast=request.forecast)
            validation = validate_dataset(dataset)
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if not validation.valid:
            raise HTTPException(status_code=422, detail={"message": "Cannot create a planning snapshot from invalid input.", "errors": _errors(validation)})
        session = app.state.sessions()
        try:
            snapshot = _new_snapshot(session, dataset, data_dir, request.forecast, validation)
            session.commit()
            session.refresh(snapshot)
            return _snapshot_response(snapshot, warnings=_warnings(validation))
        finally:
            session.close()

    @app.get("/api/snapshots/{snapshot_id}")
    def get_snapshot(snapshot_id: str):
        session = app.state.sessions()
        try:
            snapshot = _get_snapshot(session, snapshot_id)
            return _snapshot_response(snapshot)
        finally:
            session.close()

    @app.post("/api/plans/run")
    def run_plan(request: PlanRunRequest):
        session = app.state.sessions()
        try:
            snapshot = _get_snapshot(session, request.snapshot_id)
            if snapshot.validation_status == "INVALID":
                raise HTTPException(status_code=422, detail="The selected snapshot is not ready for planning.")
            plan = _persist_plan(session, snapshot, request.planning_mode, request.max_solve_time)
            session.commit()
            session.refresh(plan)
            return _plan_response(plan)
        finally:
            session.close()

    @app.get("/api/plans/{plan_id}")
    def get_plan(plan_id: str):
        session = app.state.sessions()
        try:
            plan = session.get(PlanRun, plan_id)
            if plan is None:
                raise HTTPException(status_code=404, detail=f"Plan {plan_id} was not found.")
            return _plan_response(plan)
        finally:
            session.close()

    @app.get("/api/plans/{plan_id}/unscheduled")
    def get_unscheduled(plan_id: str):
        session = app.state.sessions()
        try:
            plan = session.get(PlanRun, plan_id)
            if plan is None:
                raise HTTPException(status_code=404, detail=f"Plan {plan_id} was not found.")
            return {"plan_id": plan_id, "items": plan.payload.get("unscheduled", [])}
        finally:
            session.close()

    @app.get("/api/plans/{plan_id}/metrics")
    @app.get("/api/plans/{plan_id}/metric")
    def get_metrics(plan_id: str):
        session = app.state.sessions()
        try:
            plan = session.get(PlanRun, plan_id)
            if plan is None:
                raise HTTPException(status_code=404, detail=f"Plan {plan_id} was not found.")
            return {"plan_id": plan_id, "metrics": plan.payload.get("metrics", {}), "baseline_metrics": plan.payload.get("baseline", {}).get("metrics", {})}
        finally:
            session.close()

    @app.post("/api/plans/{plan_id}/replan")
    def replan(plan_id: str, request: ReplanRequest):
        session = app.state.sessions()
        try:
            previous = session.get(PlanRun, plan_id)
            if previous is None:
                raise HTTPException(status_code=404, detail=f"Plan {plan_id} was not found.")
            old_snapshot = _get_snapshot(session, previous.snapshot_id)
            try:
                forecast_dataset = load_dataset(old_snapshot.data_dir, goods_forecast=request.forecast)
            except (FileNotFoundError, ValueError) as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            old_dataset = dataset_from_payload(old_snapshot.payload)
            old_dataset.goods_movements = forecast_dataset.goods_movements
            validation = validate_dataset(old_dataset)
            if not validation.valid:
                raise HTTPException(status_code=422, detail={"message": "The changed forecast produced invalid input.", "errors": _errors(validation)})
            snapshot = _new_snapshot(session, old_dataset, old_snapshot.data_dir, request.forecast, validation)
            mode = request.planning_mode or previous.planning_mode
            new_plan = _persist_plan(session, snapshot, mode, request.max_solve_time, previous_plan=previous)
            new_selected = new_plan.payload.get("selected_candidates", [])
            old_selected = previous.payload.get("selected_candidates", [])
            old_intervals = {item["task_id"]: (item["start_time"], item["end_time"]) for item in old_selected}
            moved = sum(item["task_id"] in old_intervals and old_intervals[item["task_id"]] != (item["start_time"], item["end_time"]) for item in new_selected)
            newly_unscheduled = len({item["task_id"] for item in new_plan.payload.get("unscheduled", [])} - {item["task_id"] for item in previous.payload.get("unscheduled", [])})
            summary = {"previous_plan": plan_id, "new_plan": new_plan.plan_id, "scenario": f"{request.forecast.upper()}_GOODS_FORECAST", "locked_blocks_changed": 0, "tasks_moved": moved, "tasks_newly_unscheduled": newly_unscheduled, "train_impact_proxy_change": new_plan.payload["metrics"]["train_impact_proxy"] - previous.payload.get("metrics", {}).get("train_impact_proxy", 0), "warnings": []}
            new_plan.payload["change_summary"] = summary
            new_plan.status = PlanStatus.PROPOSED
            session.add(PlanEvent(plan_id=new_plan.plan_id, event_type="REPLAN_CREATED", details=summary))
            session.commit()
            session.refresh(new_plan)
            return _plan_response(new_plan)
        finally:
            session.close()

    @app.patch("/api/plans/{plan_id}/status")
    def change_status(plan_id: str, request: StatusRequest):
        session = app.state.sessions()
        try:
            plan = session.get(PlanRun, plan_id)
            if plan is None:
                raise HTTPException(status_code=404, detail=f"Plan {plan_id} was not found.")
            old_status = plan.status.value
            plan.status = request.status
            session.add(PlanEvent(plan_id=plan_id, event_type="STATUS_CHANGED", details={"from": old_status, "to": request.status.value}))
            session.commit()
            return {"plan_id": plan_id, "status": request.status.value}
        finally:
            session.close()

    @app.get("/api/plans/{plan_id}/export")
    def export_plan(plan_id: str, format: Literal["json", "csv"] = Query("json")):
        session = app.state.sessions()
        try:
            plan = session.get(PlanRun, plan_id)
            if plan is None:
                raise HTTPException(status_code=404, detail=f"Plan {plan_id} was not found.")
            if format == "json":
                return JSONResponse(content=_plan_response(plan))
            stream = io.StringIO()
            writer = csv.DictWriter(stream, fieldnames=["task_id", "block_id", "status", "reason_code"])
            writer.writeheader()
            for block in plan.payload.get("blocks", []):
                for task_id in block.get("task_ids", []):
                    writer.writerow({"task_id": task_id, "block_id": block.get("block_id"), "status": "SCHEDULED", "reason_code": ""})
            for item in plan.payload.get("unscheduled", []):
                writer.writerow({"task_id": item["task_id"], "block_id": "", "status": "UNSCHEDULED", "reason_code": item["reason_code"]})
            return Response(content=stream.getvalue(), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{plan_id}.csv"'})
        finally:
            session.close()

    return app


app = create_app()
