from __future__ import annotations

import csv
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


ScenarioTransform = Callable[[Path], None]


@dataclass(frozen=True)
class ScenarioDefinition:
    name: str
    label: str
    description: str
    expected_behavior: str
    forecast: str = "base"
    transform: ScenarioTransform | None = None
    modifications: tuple[str, ...] = ()

    @property
    def scenario_id(self) -> str:
        return self.name


def _rewrite_csv(path: Path, transform: Callable[[list[dict[str, str]]], list[dict[str, str]]]) -> None:
    with path.open(newline="", encoding="utf-8") as source:
        reader = csv.DictReader(source)
        rows = transform(list(reader))
        fieldnames = reader.fieldnames or []
    with path.open("w", newline="", encoding="utf-8") as target:
        writer = csv.DictWriter(target, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _remove_corridor_capacity(directory: Path) -> None:
    _rewrite_csv(directory / "corridor_slots.csv", lambda rows: [row for row in rows if row["slot_id"] != "SLOT-004"])


def _remove_engineering_resource(directory: Path) -> None:
    _rewrite_csv(directory / "resource_calendar.csv", lambda rows: [row for row in rows if row["department"] != "ENGINEERING"])


def _add_locked_conflict(directory: Path) -> None:
    def extend_slot(rows):
        for row in rows:
            if row["slot_id"] == "SLOT-004":
                row["end_time"] = "2026-08-28T04:30:00+05:30"
        return rows

    def extend_resource(rows):
        for row in rows:
            if row["resource_id"] == "RES-ENG-01":
                row["end_time"] = "2026-08-30T04:35:00+05:30"
        return rows

    def add_lock(rows):
        rows.append(
            {
                "commitment_id": "SCN-LOCK-ENG002",
                "section": "A-B",
                "line": "DOWN",
                "start_time": "2026-08-28T02:30:00+05:30",
                "end_time": "2026-08-28T03:15:00+05:30",
                "block_type": "FULL_BLOCK",
                "description": "Scenario lock protecting an existing commitment window",
                "locked": "true",
            }
        )
        return rows

    _rewrite_csv(directory / "corridor_slots.csv", extend_slot)
    _rewrite_csv(directory / "resource_calendar.csv", extend_resource)
    _rewrite_csv(directory / "locked_commitments.csv", add_lock)


def _add_competing_maintenance(directory: Path) -> None:
    def add_task(rows):
        rows.append(
            {
                "task_id": "SCN-ENG-001",
                "department": "ENGINEERING",
                "section": "B-C",
                "line": "UP",
                "task_type": "Competing Maintenance",
                "duration_minutes": "30",
                "earliest_start": "2026-08-27T01:00:00+05:30",
                "latest_finish": "2026-08-27T03:30:00+05:30",
                "criticality": "1",
                "defect_severity": "1",
                "asset_criticality": "1",
                "failure_consequence": "1",
                "deferral_history": "0",
                "mandatory": "false",
                "requires_traffic_block": "true",
                "requires_power_isolation": "false",
                "requires_snt_disconnection": "false",
            }
        )
        return rows

    _rewrite_csv(directory / "tms_tasks.csv", add_task)


def _add_corridor_closure(directory: Path) -> None:
    """Use the existing locked-commitment model for a temporary closure."""
    def add_closure(rows):
        rows.append({
            "commitment_id": "SCN-CLOSURE-AB-UP",
            "section": "A-B", "line": "UP",
            "start_time": "2026-08-28T00:30:00+05:30",
            "end_time": "2026-08-28T02:00:00+05:30",
            "block_type": "FULL_BLOCK",
            "description": "Scenario corridor closure", "locked": "true",
        })
        return rows
    _rewrite_csv(directory / "locked_commitments.csv", add_closure)


SCENARIOS = {
    "base": ScenarioDefinition(
        "base", "Base", "Unmodified synthetic reference dataset.", "The pipeline should return a valid optimal or feasible plan.", modifications=("none",),
    ),
    "missing_corridor": ScenarioDefinition(
        "missing_corridor", "Missing Corridor Capacity", "Removes SLOT-004, the only compatible window for ENG-002.", "ENG-002 should have no candidates and the mandatory schedule should be infeasible.", transform=_remove_corridor_capacity, modifications=("remove SLOT-004",),
    ),
    "resource_unavailable": ScenarioDefinition(
        "resource_unavailable", "Resource Unavailable", "Removes the Engineering resource pool from the calendar.", "Engineering candidates should be rejected for resource unavailability; mandatory Engineering work cannot be scheduled.", transform=_remove_engineering_resource, modifications=("remove Engineering resource availability",),
    ),
    "locked_commitment": ScenarioDefinition(
        "locked_commitment", "Locked Commitment Conflict", "Adds a locked A-B DOWN commitment over ENG-002's reference window and extends the local envelope so a later candidate remains possible.", "The lock must remain protected and ENG-002 should move to a later valid candidate.", transform=_add_locked_conflict, modifications=("add SCN-LOCK-ENG002",),
    ),
    "stressed_goods": ScenarioDefinition(
        "stressed_goods", "Stressed Goods Forecast", "Uses the existing goods_forecast_stressed.csv without changing base inputs.", "The stressed forecast should be processed honestly and produce either a valid result or an explicit infeasible/invalid result.", forecast="stressed", modifications=("use stressed goods forecast",),
    ),
    "competing_maintenance": ScenarioDefinition(
        "competing_maintenance", "Competing Maintenance", "Adds one optional Engineering task competing for the B-C UP corridor and Engineering resource.", "CP-SAT should preserve mandatory feasibility and avoid corridor/resource overlap; the optional task may be rejected.", transform=_add_competing_maintenance, modifications=("add SCN-ENG-001",),
    ),
    "corridor_closure": ScenarioDefinition(
        "corridor_closure", "Corridor Closure", "Adds a temporary locked full-block closure on A-B UP.", "Affected candidates should be removed while mandatory feasibility remains enforced.", transform=_add_corridor_closure, modifications=("close A-B UP from 00:30 to 02:00",),
    ),
}


def scenario_definition(name: str) -> ScenarioDefinition:
    try:
        return SCENARIOS[name]
    except KeyError as exc:
        raise ValueError(f"Unknown scenario: {name}. Available scenarios: {', '.join(SCENARIOS)}") from exc


def available_scenarios() -> list[dict[str, str]]:
    return [
        {"name": definition.name, "label": definition.label, "description": definition.description, "expected_behavior": definition.expected_behavior, "forecast": definition.forecast, "modifications": list(definition.modifications)}
        for definition in SCENARIOS.values()
    ]


def materialize_scenario(name: str, destination: str | Path, base_dir: str | Path | None = None) -> Path:
    """Copy base fixtures to a temp directory and apply only this scenario's delta."""
    definition = scenario_definition(name)
    base = Path(base_dir) if base_dir else Path(__file__).resolve().parents[3] / "data" / "synthetic"
    destination = Path(destination)
    if destination.exists():
        raise FileExistsError(f"Scenario destination already exists: {destination}")
    shutil.copytree(base, destination)
    if definition.transform:
        definition.transform(destination)
    return destination
