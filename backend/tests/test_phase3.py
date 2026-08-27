from pathlib import Path

from app.loaders import load_dataset
from app.validation import create_snapshot, validate_dataset


DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "synthetic"


def test_base_dataset_is_ready():
    dataset = load_dataset(DATA_DIR, goods_forecast="base")
    result = validate_dataset(dataset)
    assert result.valid
    assert result.status == "READY"
    assert not result.errors


def test_duplicate_task_id_is_rejected():
    dataset = load_dataset(DATA_DIR, goods_forecast="base")
    dataset.engineering_tasks.append(dataset.engineering_tasks[0])
    result = validate_dataset(dataset)
    assert not result.valid
    assert any(issue.code == "DUPLICATE_ID" and issue.entity_id == "ENG-001" for issue in result.errors)


def test_invalid_section_is_rejected():
    dataset = load_dataset(DATA_DIR, goods_forecast="base")
    dataset.engineering_tasks[0].section = "B-D"  # Pydantic objects are mutable by default.
    result = validate_dataset(dataset)
    assert any(issue.code == "INVALID_SECTION" for issue in result.errors)


def test_snapshot_requires_valid_dataset():
    dataset = load_dataset(DATA_DIR, goods_forecast="base")
    result = validate_dataset(dataset)
    snapshot = create_snapshot(dataset, result, "SNAP-001", "base")
    assert snapshot.snapshot_id == "SNAP-001"
    assert snapshot.validation_status == "READY"
    assert snapshot.source_counts["engineering_tasks"] == 5
