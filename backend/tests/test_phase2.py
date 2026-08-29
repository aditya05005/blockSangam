from datetime import datetime
from pathlib import Path

import pytest

from app.domain.models import Department, Line, Task
from app.loaders import load_dataset


DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "synthetic"


def test_task_model_rejects_invalid_window():
    with pytest.raises(ValueError):
        Task(
            task_id="BAD-001",
            department=Department.ENGINEERING,
            section="B-C",
            line=Line.UP,
            task_type="Test",
            duration_minutes=30,
            earliest_start=datetime.fromisoformat("2026-08-27T02:00:00+05:30"),
            latest_finish=datetime.fromisoformat("2026-08-27T01:00:00+05:30"),
            criticality=1,
            defect_severity=1,
            asset_criticality=1,
            failure_consequence=1,
            deferral_history=0,
            mandatory=False,
            requires_traffic_block=True,
            requires_power_isolation=False,
            requires_snt_disconnection=False,
        )


def test_full_base_dataset_loads_without_errors():
    dataset = load_dataset(DATA_DIR, goods_forecast="base")

    assert not dataset.errors
    assert len(dataset.engineering_tasks) == 10
    assert len(dataset.snt_tasks) == 8
    assert len(dataset.trd_tasks) == 7
    assert len(dataset.passenger_movements) == 10
    assert len(dataset.goods_movements) == 3
    # The base capacity plus seven Mumbai coordination windows.
    assert len(dataset.corridor_slots) == 15
    assert len(dataset.resources) == 5
    assert len(dataset.locked_commitments) == 3
    assert len(dataset.tasks) == 25
    assert len(dataset.movements) == 13


def test_stressed_forecast_adds_goods_movement():
    base = load_dataset(DATA_DIR, goods_forecast="base")
    stressed = load_dataset(DATA_DIR, goods_forecast="stressed")

    assert not base.errors
    assert not stressed.errors
    assert len(stressed.goods_movements) == len(base.goods_movements) + 1
    assert any(m.movement_id == "GF-017" for m in stressed.goods_movements)
