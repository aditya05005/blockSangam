from datetime import datetime, timezone

from app.domain.models import Department, Line, Task
from app.priority import PriorityConfig, PriorityEngine, calculate_score


def make_task(task_id: str, value: int = 3, *, mandatory: bool = False, deferral: int = 0) -> Task:
    return Task(
        task_id=task_id,
        department=Department.ENGINEERING,
        section="B-C",
        line=Line.UP,
        task_type="Test",
        duration_minutes=30,
        earliest_start=datetime(2026, 8, 27, 1, 0, tzinfo=timezone.utc),
        latest_finish=datetime(2026, 8, 27, 4, 0, tzinfo=timezone.utc),
        criticality=value,
        defect_severity=value,
        asset_criticality=value,
        failure_consequence=value,
        deferral_history=deferral,
        mandatory=mandatory,
        requires_traffic_block=True,
        requires_power_isolation=False,
        requires_snt_disconnection=False,
    )


def test_high_risk_task_scores_higher_than_low_risk_task():
    config = PriorityConfig()
    low, _ = calculate_score(make_task("LOW", 1), config)
    high, _ = calculate_score(make_task("HIGH", 5), config)
    assert high > low


def test_deferral_history_increases_priority():
    config = PriorityConfig()
    fresh, _ = calculate_score(make_task("FRESH", 3, deferral=0), config)
    deferred, _ = calculate_score(make_task("DEFERRED", 3, deferral=3), config)
    assert deferred > fresh


def test_mandatory_flag_is_preserved_and_bonus_applied():
    config = PriorityConfig()
    optional, _ = calculate_score(make_task("OPTIONAL", 3), config)
    mandatory, _ = calculate_score(make_task("MANDATORY", 3, mandatory=True), config)
    assert mandatory > optional
    assert PriorityEngine(config).score_task(make_task("M", 3, mandatory=True)).mandatory


def test_score_is_explainable_and_bounded():
    config = PriorityConfig()
    score, components = calculate_score(make_task("MAX", 5, mandatory=True, deferral=99), config)
    assert score == 1.0
    assert components.total > 1.0


def test_ranking_is_deterministic():
    engine = PriorityEngine()
    tasks = [
        make_task("B", 3),
        make_task("A", 3),
        make_task("C", 5, mandatory=True),
    ]
    ranked = engine.rank(tasks)
    assert [item.task_id for item in ranked] == ["C", "A", "B"]


def test_weight_configuration_changes_score():
    default = PriorityConfig()
    criticality_heavy = PriorityConfig(
        criticality_weight=0.60,
        defect_severity_weight=0.10,
        asset_criticality_weight=0.10,
        failure_consequence_weight=0.10,
        deferral_history_weight=0.10,
    )
    task = make_task("T", 5)
    default_score, _ = calculate_score(task, default)
    changed_score, _ = calculate_score(task, criticality_heavy)
    assert changed_score == default_score
