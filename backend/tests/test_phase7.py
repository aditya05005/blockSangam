from datetime import datetime, timezone

from app.blocks import JointBlockBuilder
from app.candidates.models import Candidate, CandidateGenerationResult
from app.domain.models import Line


def candidate(cid, tid, start, end, section="B-C", line=Line.UP, resources=()):
    base = datetime(2026, 8, 27, 0, tzinfo=timezone.utc)
    return Candidate(cid, tid, "S1", base.replace(hour=start), base.replace(hour=end), section, line, resources)


def test_overlapping_compatible_candidates_are_grouped():
    result = JointBlockBuilder().build(CandidateGenerationResult([
        candidate("C1", "T1", 1, 2, resources=("R1",)),
        candidate("C2", "T2", 1, 2, resources=("R2",)),
    ]))
    assert result.block_count == 1
    assert set(result.joint_blocks[0].task_ids) == {"T1", "T2"}


def test_sequential_contiguous_candidates_share_a_block():
    result = JointBlockBuilder().build(CandidateGenerationResult([
        candidate("C1", "T1", 1, 2, resources=("R1",)),
        candidate("C2", "T2", 2, 3, resources=("R2",)),
    ]))
    assert result.block_count == 1
    assert result.joint_blocks[0].start_time.hour == 1
    assert result.joint_blocks[0].end_time.hour == 3


def test_different_sections_do_not_group():
    result = JointBlockBuilder().build(CandidateGenerationResult([
        candidate("C1", "T1", 1, 2, section="A-B"),
        candidate("C2", "T2", 1, 2, section="B-C"),
    ]))
    assert result.block_count == 2


def test_different_lines_do_not_group():
    result = JointBlockBuilder().build(CandidateGenerationResult([
        candidate("C1", "T1", 1, 2, line=Line.UP),
        candidate("C2", "T2", 1, 2, line=Line.DOWN),
    ]))
    assert result.block_count == 2


def test_shared_resource_overlap_does_not_group():
    result = JointBlockBuilder().build(CandidateGenerationResult([
        candidate("C1", "T1", 1, 2, resources=("R1",)),
        candidate("C2", "T2", 1, 2, resources=("R1",)),
    ]))
    assert result.block_count == 2
    assert any(r.reason_code == "RESOURCE_CONFLICT" for r in result.rejections)


def test_gap_between_candidates_does_not_group():
    result = JointBlockBuilder().build(CandidateGenerationResult([
        candidate("C1", "T1", 1, 2, resources=("R1",)),
        candidate("C2", "T2", 3, 4, resources=("R2",)),
    ]))
    assert result.block_count == 2
