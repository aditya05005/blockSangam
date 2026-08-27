from datetime import datetime, timezone

from app.candidates.models import Candidate, CandidateGenerationResult
from app.domain.models import Department, Line, Task
from app.loaders import CanonicalDataset
from app.priority import PriorityEngine
from app.scheduler import CPSATScheduler, ScheduleStatus


def task(task_id, score=5, mandatory=False):
    return Task(
        task_id=task_id, department=Department.ENGINEERING, section="B-C", line=Line.UP,
        task_type="Test", duration_minutes=30,
        earliest_start=datetime(2026, 8, 27, 1, tzinfo=timezone.utc), latest_finish=datetime(2026, 8, 27, 4, tzinfo=timezone.utc),
        criticality=score, defect_severity=score, asset_criticality=score, failure_consequence=score,
        deferral_history=0, mandatory=mandatory, requires_traffic_block=True,
        requires_power_isolation=False, requires_snt_disconnection=False,
    )


def candidate(cid, tid, start_hour, resource="R1"):
    start = datetime(2026, 8, 27, start_hour, tzinfo=timezone.utc)
    return Candidate(cid, tid, "S1", start, start.replace(hour=start_hour, minute=30), "B-C", Line.UP, (resource,))


def ds(tasks):
    return CanonicalDataset(tasks, [], [], [], [], [], [], [], [])


def test_selects_feasible_candidate():
    tasks = [task("A")]
    result = CPSATScheduler().solve(ds(tasks), CandidateGenerationResult([candidate("C1", "A", 1)], []))
    assert result.status == ScheduleStatus.OPTIMAL
    assert [c.candidate_id for c in result.selected_candidates] == ["C1"]


def test_mandatory_task_must_be_selected():
    tasks = [task("A", mandatory=True)]
    candidates = CandidateGenerationResult([candidate("C1", "A", 1), candidate("C2", "A", 2)], [])
    result = CPSATScheduler().solve(ds(tasks), candidates)
    assert result.status == ScheduleStatus.OPTIMAL
    assert len(result.selected_candidates) == 1


def test_higher_priority_task_wins_resource_conflict():
    tasks = [task("LOW", 1), task("HIGH", 5)]
    candidates = CandidateGenerationResult([candidate("C1", "LOW", 1), candidate("C2", "HIGH", 1)], [])
    result = CPSATScheduler().solve(ds(tasks), candidates)
    assert [c.task_id for c in result.selected_candidates] == ["HIGH"]


def test_overlapping_same_corridor_candidates_cannot_both_be_selected():
    tasks = [task("A", 5), task("B", 4)]
    candidates = CandidateGenerationResult([candidate("C1", "A", 1), candidate("C2", "B", 1)], [])
    result = CPSATScheduler().solve(ds(tasks), candidates)
    assert len(result.selected_candidates) == 1


def test_missing_mandatory_candidate_is_infeasible():
    tasks = [task("A", mandatory=True)]
    result = CPSATScheduler().solve(ds(tasks), CandidateGenerationResult([], []))
    assert result.status == ScheduleStatus.INFEASIBLE
    assert result.unscheduled_mandatory_task_ids == ("A",)


def test_same_resource_overlapping_candidates_conflict_even_on_different_corridors():
    a = task("A", 5)
    b = task("B", 4)
    b.section = "A-B"
    candidates = CandidateGenerationResult([candidate("C1", "A", 1, "R1"), candidate("C2", "B", 1, "R1")], [])
    result = CPSATScheduler().solve(ds([a, b]), candidates)
    assert len(result.selected_candidates) == 1
