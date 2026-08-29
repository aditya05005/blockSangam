from datetime import datetime, timezone

from app.domain.models import Department, Line, Task
from app.priority import PriorityEngine


def make_task(task_id: str, value: int = 3, *, mandatory: bool = False, deferral: int = 0) -> Task:
    return Task(
        task_id=task_id, department=Department.ENGINEERING, section="B-C", line=Line.UP,
        task_type="Test", duration_minutes=30,
        earliest_start=datetime(2026, 8, 27, 1, tzinfo=timezone.utc),
        latest_finish=datetime(2026, 8, 27, 4, tzinfo=timezone.utc),
        criticality=value, defect_severity=value, asset_criticality=value,
        failure_consequence=value, deferral_history=deferral, mandatory=mandatory,
        requires_traffic_block=True, requires_power_isolation=False,
        requires_snt_disconnection=False,
    )


def test_ml_model_is_the_authoritative_priority_source():
    result = PriorityEngine().score_task(make_task("ML-001", 4))
    assert result.prediction_source == "ML_MODEL"
    assert result.score == result.ml_score
    assert result.model_version.startswith("outcome-risk-rf-")


def test_ml_risk_increases_across_distinct_task_profiles():
    engine = PriorityEngine()
    low = engine.score_task(make_task("LOW", 1))
    medium = engine.score_task(make_task("MID", 3, deferral=2))
    high = engine.score_task(make_task("HIGH", 5, mandatory=True, deferral=7))
    assert low.score < medium.score < high.score
    assert all(0 <= item.score <= 1 for item in (low, medium, high))


def test_ml_output_is_explainable_and_calibrated():
    results = [PriorityEngine().score_task(make_task(f"T-{value}", value, deferral=value)) for value in range(1, 6)]
    assert all(item.factors for item in results)
    assert all(0.35 <= item.confidence <= 0.88 for item in results)
    assert len({item.confidence for item in results}) > 1


def test_ml_ranking_is_deterministic_and_preserves_mandatory_constraint_order():
    engine = PriorityEngine()
    tasks = [make_task("B", 3), make_task("A", 3), make_task("C", 5, mandatory=True)]
    first = engine.rank(tasks)
    second = engine.rank(tasks)
    assert [item.task_id for item in first] == [item.task_id for item in second]
    assert first[0].task_id == "C"
