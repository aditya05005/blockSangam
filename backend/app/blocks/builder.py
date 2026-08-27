from collections import defaultdict

from app.candidates.models import Candidate, CandidateGenerationResult
from .compatibility import can_share_block
from .models import BlockPlanningResult, BlockRejection, JointBlock


class JointBlockBuilder:
    """Build safe joint blocks from already-selected Phase 6 candidates.

    This MVP uses deterministic greedy grouping: candidates are ordered by
    corridor and start time, then compatible candidates are packed into the
    same block. It never changes task timing and never merges across corridors.
    """

    def build(self, candidates: CandidateGenerationResult) -> BlockPlanningResult:
        result = BlockPlanningResult()
        ordered = sorted(candidates.candidates, key=lambda c: (c.section, c.line.value, c.start_time, c.end_time, c.candidate_id))
        groups: list[list[Candidate]] = []

        for candidate in ordered:
            placed = False
            for group in groups:
                compatible = True
                for existing in group:
                    ok, code, message = can_share_block(existing, candidate)
                    if not ok and code != "NO_TIME_OVERLAP":
                        result.rejections.append(BlockRejection((existing.candidate_id, candidate.candidate_id), code, message))
                        compatible = False
                        break
                if compatible and _can_extend_group(group, candidate):
                    group.append(candidate)
                    placed = True
                    break
            if not placed:
                groups.append([candidate])

        for number, group in enumerate(groups, 1):
            section = group[0].section
            line = group[0].line
            result.joint_blocks.append(
                JointBlock(
                    block_id=f"JB-{number:04d}",
                    section=section,
                    line=line,
                    start_time=min(c.start_time for c in group),
                    end_time=max(c.end_time for c in group),
                    candidate_ids=tuple(c.candidate_id for c in group),
                    task_ids=tuple(c.task_id for c in group),
                    resource_ids=tuple(sorted({r for c in group for r in c.resource_ids})),
                )
            )

        return result


def _can_extend_group(group: list[Candidate], candidate: Candidate) -> bool:
    if not group:
        return True
    first = group[0]
    if first.section != candidate.section or first.line != candidate.line:
        return False
    # A joint block represents a shared operational window. Candidates that
    # are sequential but leave a gap are not merged in this MVP.
    group_start = min(c.start_time for c in group)
    group_end = max(c.end_time for c in group)
    return candidate.start_time <= group_end and candidate.end_time >= group_start
