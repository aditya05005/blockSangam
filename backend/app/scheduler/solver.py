from time import monotonic

from ortools.sat.python import cp_model

from app.candidates.models import Candidate, CandidateGenerationResult
from app.domain.models import LockedCommitment
from app.loaders import CanonicalDataset
from app.priority import PriorityEngine
from .models import ScheduleResult, ScheduleStatus


class CPSATScheduler:
    def __init__(self, priority_engine: PriorityEngine | None = None, max_time_seconds: float = 10.0):
        self.priority_engine = priority_engine or PriorityEngine()
        if max_time_seconds <= 0:
            raise ValueError("max_time_seconds must be positive")
        self.max_time_seconds = max_time_seconds

    def solve(self, dataset: CanonicalDataset, candidates: CandidateGenerationResult) -> ScheduleResult:
        start = monotonic()
        tasks = {task.task_id: task for task in dataset.tasks}
        mandatory = tuple(task.task_id for task in dataset.tasks if task.mandatory)
        missing = tuple(sorted(task_id for task_id in mandatory if not any(c.task_id == task_id for c in candidates.candidates)))
        if missing:
            return ScheduleResult(ScheduleStatus.INFEASIBLE, message="Mandatory task has no feasible candidate.", unscheduled_mandatory_task_ids=missing, solve_time_seconds=monotonic() - start)

        model = cp_model.CpModel()
        candidate_vars = {c.candidate_id: model.NewBoolVar(f"select_{c.candidate_id}") for c in candidates.candidates}
        by_task: dict[str, list] = {}
        for candidate in candidates.candidates:
            by_task.setdefault(candidate.task_id, []).append(candidate_vars[candidate.candidate_id])
        for task_id, vars_ in by_task.items():
            model.Add(sum(vars_) == 1 if tasks[task_id].mandatory else sum(vars_) <= 1)

        # Candidates sharing a physical section/line and overlapping in time
        # cannot both be selected when either one imposes a traffic block.
        for i, left in enumerate(candidates.candidates):
            for right in candidates.candidates[i + 1:]:
                if _candidate_overlap(left, right) and _same_corridor(left, right):
                    model.Add(candidate_vars[left.candidate_id] + candidate_vars[right.candidate_id] <= 1)
                elif set(left.resource_ids) & set(right.resource_ids) and _interval_overlap(left, right):
                    model.Add(candidate_vars[left.candidate_id] + candidate_vars[right.candidate_id] <= 1)

        # Locked commitments are rechecked defensively at the optimizer boundary.
        for candidate in candidates.candidates:
            for lock in dataset.locked_commitments:
                if lock.locked and _overlap_with_lock(candidate, lock):
                    model.Add(candidate_vars[candidate.candidate_id] == 0)

        scores = {r.task_id: r.score for r in self.priority_engine.rank(dataset.tasks)}
        # Fixed-point integer objective avoids floating point coefficients in CP-SAT.
        objective_terms = [candidate_vars[c.candidate_id] * int(round(scores[c.task_id] * 1_000_000)) for c in candidates.candidates]
        model.Maximize(sum(objective_terms))

        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = self.max_time_seconds
        solver.parameters.num_search_workers = 1
        status = solver.Solve(model)
        elapsed = monotonic() - start

        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            return ScheduleResult(ScheduleStatus.INFEASIBLE if status == cp_model.INFEASIBLE else ScheduleStatus.UNKNOWN, solve_time_seconds=elapsed, message="No feasible schedule found.")

        selected = tuple(c for c in candidates.candidates if solver.Value(candidate_vars[c.candidate_id]))
        value = sum(scores[c.task_id] for c in selected)
        return ScheduleResult(
            status=ScheduleStatus.OPTIMAL if status == cp_model.OPTIMAL else ScheduleStatus.FEASIBLE,
            selected_candidates=selected,
            objective_value=round(value, 6),
            solve_time_seconds=elapsed,
            message="Schedule generated successfully.",
        )


def _interval_overlap(a: Candidate, b: Candidate) -> bool:
    return a.start_time < b.end_time and b.start_time < a.end_time


def _candidate_overlap(a: Candidate, b: Candidate) -> bool:
    return _interval_overlap(a, b)


def _same_corridor(a: Candidate, b: Candidate) -> bool:
    return a.section == b.section and a.line == b.line


def _overlap_with_lock(candidate: Candidate, lock: LockedCommitment) -> bool:
    return candidate.section == lock.section and candidate.line == lock.line and candidate.start_time < lock.end_time and lock.start_time < candidate.end_time
