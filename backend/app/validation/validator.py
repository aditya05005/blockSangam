from collections import Counter

from app.candidates.models import CandidateGenerationResult
from app.domain.models import Task
from app.loaders import CanonicalDataset
from app.blocks.models import BlockPlanningResult
from .models import RepairAction, ValidationIssue, ValidationResult, ValidationSeverity


class ScheduleValidator:
    """Independently validate the Phase 7 schedule.

    Validation is deliberately read-only by default. `repair=True` enables a
    conservative repair pass that removes invalid scheduled entries and then
    revalidates the repaired schedule. It never moves or invents a task.
    """

    def validate(
        self,
        dataset: CanonicalDataset,
        blocks: BlockPlanningResult,
        candidates: CandidateGenerationResult,
        *,
        repair: bool = False,
    ) -> ValidationResult:
        result = self._validate(dataset, blocks, candidates)
        if not repair or result.valid:
            return result

        repaired_blocks, actions = self._repair(dataset, blocks, candidates)
        repaired = self._validate(dataset, repaired_blocks, candidates)
        repaired.repaired = bool(actions)
        repaired.repair_actions = actions
        repaired.checked_tasks = result.checked_tasks
        repaired.checked_blocks = len(repaired_blocks.joint_blocks)
        return repaired

    def _validate(self, dataset, blocks, candidates):
        result = ValidationResult(valid=True, checked_tasks=len(dataset.tasks), checked_blocks=len(blocks.joint_blocks))
        task_map = {t.task_id: t for t in dataset.tasks}
        candidate_map = {c.candidate_id: c for c in candidates.candidates}
        scheduled = []

        seen_tasks = Counter()
        seen_candidates = set()
        for block in blocks.joint_blocks:
            if not block.candidate_ids:
                self._error(result, "EMPTY_BLOCK", "Joint block contains no candidates.", block_id=block.block_id)
                continue
            if block.start_time >= block.end_time:
                self._error(result, "INVALID_BLOCK_WINDOW", "Joint block has an invalid time window.", block_id=block.block_id)
            block_candidates = []
            for cid in block.candidate_ids:
                candidate = candidate_map.get(cid)
                if candidate is None:
                    self._error(result, "UNKNOWN_CANDIDATE", f"Candidate {cid} is not present in the Phase 5 candidate set.", block_id=block.block_id, candidate_ids=(cid,))
                    continue
                if cid in seen_candidates:
                    self._error(result, "CANDIDATE_DUPLICATED", f"Candidate {cid} appears in multiple blocks.", block_id=block.block_id, candidate_ids=(cid,))
                seen_candidates.add(cid)
                block_candidates.append(candidate)
                scheduled.append(candidate)
                seen_tasks[candidate.task_id] += 1
                task = task_map.get(candidate.task_id)
                if task is None:
                    self._error(result, "UNKNOWN_TASK", f"Candidate {cid} references an unknown task.", block_id=block.block_id, candidate_ids=(cid,))
                    continue
                if candidate.start_time < task.earliest_start or candidate.end_time > task.latest_finish:
                    self._error(result, "TASK_OUTSIDE_ALLOWED_WINDOW", f"Candidate {cid} falls outside task {task.task_id}'s allowed window.", task_ids=(task.task_id,), candidate_ids=(cid,), block_id=block.block_id)
                slot = next((s for s in dataset.corridor_slots if s.slot_id == candidate.slot_id), None)
                if slot is None or candidate.section != slot.section or candidate.line != slot.line or candidate.start_time < slot.start_time or candidate.end_time > slot.end_time:
                    self._error(result, "INVALID_CORRIDOR_SLOT", f"Candidate {cid} is outside its corridor slot.", task_ids=(task.task_id,), candidate_ids=(cid,), block_id=block.block_id)

            for i, left in enumerate(block_candidates):
                for right in block_candidates[i + 1:]:
                    if left.start_time < right.end_time and right.start_time < left.end_time and set(left.resource_ids) & set(right.resource_ids):
                        self._error(result, "RESOURCE_CAPACITY_EXCEEDED", "Overlapping candidates exceed shared resource capacity.", task_ids=(left.task_id, right.task_id), candidate_ids=(left.candidate_id, right.candidate_id), block_id=block.block_id)

        for task in dataset.tasks:
            count = seen_tasks[task.task_id]
            if count > 1:
                self._error(result, "TASK_DUPLICATED", f"Task {task.task_id} is scheduled more than once.", task_ids=(task.task_id,))
            if task.mandatory and count != 1:
                self._error(result, "MANDATORY_TASK_UNSCHEDULED", f"Mandatory task {task.task_id} is not scheduled exactly once.", task_ids=(task.task_id,))

        for candidate in scheduled:
            task = task_map.get(candidate.task_id)
            if not task or not task.requires_traffic_block:
                continue
            for movement in dataset.movements:
                if candidate.section == movement.section and candidate.line == movement.line and candidate.start_time < movement.end_time and movement.start_time < candidate.end_time:
                    self._error(result, "TRAIN_MOVEMENT_CONFLICT", f"Candidate {candidate.candidate_id} overlaps movement {movement.movement_id}.", task_ids=(candidate.task_id,), candidate_ids=(candidate.candidate_id,))
            for lock in dataset.locked_commitments:
                if lock.locked and candidate.section == lock.section and candidate.line == lock.line and candidate.start_time < lock.end_time and lock.start_time < candidate.end_time:
                    self._error(result, "LOCKED_COMMITMENT_CONFLICT", f"Candidate {candidate.candidate_id} overlaps locked commitment {lock.commitment_id}.", task_ids=(candidate.task_id,), candidate_ids=(candidate.candidate_id,))

        result.valid = not result.errors
        return result

    def _repair(self, dataset, blocks, candidates):
        """Remove invalid candidate assignments; never alter source candidates."""
        candidate_map = {c.candidate_id: c for c in candidates.candidates}
        task_map = {t.task_id: t for t in dataset.tasks}
        actions = []
        kept = []

        for block in blocks.joint_blocks:
            valid_ids = []
            for cid in block.candidate_ids:
                candidate = candidate_map.get(cid)
                reason = self._first_conflict(dataset, candidate, task_map) if candidate else ("UNKNOWN_CANDIDATE", "Candidate does not exist.")
                if reason:
                    actions.append(RepairAction("REMOVE_CANDIDATE", cid, block.block_id, reason[0], reason[1]))
                else:
                    valid_ids.append(cid)
            if valid_ids:
                new_candidates = [candidate_map[cid] for cid in valid_ids]
                block = type(block)(
                    block_id=block.block_id,
                    section=block.section,
                    line=block.line,
                    start_time=min(c.start_time for c in new_candidates),
                    end_time=max(c.end_time for c in new_candidates),
                    candidate_ids=tuple(valid_ids),
                    task_ids=tuple(c.task_id for c in new_candidates),
                    resource_ids=tuple(sorted({r for c in new_candidates for r in c.resource_ids})),
                    block_type=block.block_type,
                    traffic_block=block.traffic_block,
                    power_isolation=block.power_isolation,
                    snt_disconnection=block.snt_disconnection,
                )
                kept.append(block)
            else:
                actions.append(RepairAction("REMOVE_BLOCK", None, block.block_id, "EMPTY_AFTER_REPAIR", "Block became empty after conflicting candidates were removed."))

        # Resolve duplicate task assignments deterministically: keep the first
        # assignment and remove later ones. This does not move the task.
        seen = set()
        final_blocks = []
        for block in kept:
            ids = []
            for cid in block.candidate_ids:
                task_id = candidate_map[cid].task_id
                if task_id in seen:
                    actions.append(RepairAction("REMOVE_CANDIDATE", cid, block.block_id, "TASK_DUPLICATED", "Later duplicate task assignment removed."))
                else:
                    seen.add(task_id)
                    ids.append(cid)
            if ids:
                cs = [candidate_map[cid] for cid in ids]
                final_blocks.append(type(block)(block.block_id, block.section, block.line, min(c.start_time for c in cs), max(c.end_time for c in cs), tuple(ids), tuple(c.task_id for c in cs), tuple(sorted({r for c in cs for r in c.resource_ids})), block.block_type, block.traffic_block, block.power_isolation, block.snt_disconnection))
        return BlockPlanningResult(joint_blocks=final_blocks), actions

    def _first_conflict(self, dataset, candidate, task_map):
        if candidate is None:
            return "UNKNOWN_CANDIDATE", "Candidate does not exist."
        task = task_map.get(candidate.task_id)
        if task is None:
            return "UNKNOWN_TASK", "Candidate references an unknown task."
        if candidate.start_time < task.earliest_start or candidate.end_time > task.latest_finish:
            return "TASK_OUTSIDE_ALLOWED_WINDOW", "Candidate falls outside task window."
        slot = next((s for s in dataset.corridor_slots if s.slot_id == candidate.slot_id), None)
        if slot is None or candidate.section != slot.section or candidate.line != slot.line or candidate.start_time < slot.start_time or candidate.end_time > slot.end_time:
            return "INVALID_CORRIDOR_SLOT", "Candidate falls outside its corridor slot."
        if task.requires_traffic_block:
            for movement in dataset.movements:
                if candidate.section == movement.section and candidate.line == movement.line and candidate.start_time < movement.end_time and movement.start_time < candidate.end_time:
                    return "TRAIN_MOVEMENT_CONFLICT", f"Candidate overlaps movement {movement.movement_id}."
            for lock in dataset.locked_commitments:
                if lock.locked and candidate.section == lock.section and candidate.line == lock.line and candidate.start_time < lock.end_time and lock.start_time < candidate.end_time:
                    return "LOCKED_COMMITMENT_CONFLICT", f"Candidate overlaps locked commitment {lock.commitment_id}."
        return None

    @staticmethod
    def _error(result, code, message, task_ids=(), candidate_ids=(), block_id=None):
        result.errors.append(ValidationIssue(code, ValidationSeverity.ERROR, message, task_ids, candidate_ids, block_id))
