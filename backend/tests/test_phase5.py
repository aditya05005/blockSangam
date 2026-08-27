from datetime import datetime, timezone, timedelta

from app.candidates import CandidateGenerator
from app.domain.models import CorridorSlot, Department, Line, Resource, ResourceType, Task, TrainMovement, MovementType
from app.loaders import CanonicalDataset


def task(**overrides):
    data = dict(
        task_id="T-001", department=Department.ENGINEERING, section="B-C", line=Line.UP,
        task_type="Test", duration_minutes=60,
        earliest_start=datetime(2026, 8, 27, 1, tzinfo=timezone.utc),
        latest_finish=datetime(2026, 8, 27, 4, tzinfo=timezone.utc),
        criticality=3, defect_severity=3, asset_criticality=3, failure_consequence=3,
        deferral_history=0, mandatory=False, requires_traffic_block=True,
        requires_power_isolation=False, requires_snt_disconnection=False,
    )
    data.update(overrides)
    return Task(**data)


def slot(**overrides):
    data = dict(
        slot_id="S-001", section="B-C", line=Line.UP,
        start_time=datetime(2026, 8, 27, 0, tzinfo=timezone.utc),
        end_time=datetime(2026, 8, 27, 4, tzinfo=timezone.utc),
        block_type="FULL_BLOCK", traffic_block=True, power_isolation=True, snt_disconnection=True,
    )
    data.update(overrides)
    return CorridorSlot(**data)


def resource():
    return Resource(
        resource_id="R-001", department=Department.ENGINEERING, resource_type=ResourceType.TEAM,
        resource_name="Engineering Team", start_time=datetime(2026, 8, 27, 0, tzinfo=timezone.utc),
        end_time=datetime(2026, 8, 27, 6, tzinfo=timezone.utc), capacity=1,
    )


def dataset(tasks, slots=None, movements=None, locks=None):
    return CanonicalDataset(tasks, [], [], [], movements or [], slots or [slot()], [resource()], locks or [], [])


def test_generates_half_hour_candidates():
    result = CandidateGenerator(30).generate(dataset([task()]))
    assert [(c.start_time.hour, c.start_time.minute) for c in result.candidates] == [(1, 0), (1, 30), (2, 0), (2, 30), (3, 0)]


def test_wrong_section_is_rejected():
    result = CandidateGenerator().generate(dataset([task(section="A-B")]))
    assert not result.candidates
    assert any(r.reason_code == "SECTION_MISMATCH" for r in result.rejections)


def test_missing_block_capability_is_rejected():
    result = CandidateGenerator().generate(dataset([task(requires_power_isolation=True)], [slot(power_isolation=False)]))
    assert not result.candidates
    assert any(r.reason_code == "POWER_ISOLATION_REQUIRED" for r in result.rejections)


def test_movement_conflict_is_rejected():
    movement = TrainMovement(
        movement_id="M-001", movement_type=MovementType.PASSENGER, section="B-C", line=Line.UP,
        start_time=datetime(2026, 8, 27, 1, 30, tzinfo=timezone.utc),
        end_time=datetime(2026, 8, 27, 1, 45, tzinfo=timezone.utc),
    )
    result = CandidateGenerator().generate(dataset([task()], movements=[movement]))
    assert all(not (c.start_time <= movement.start_time < c.end_time) for c in result.candidates)
    assert any(r.reason_code == "MOVEMENT_CONFLICT" for r in result.rejections)


def test_locked_commitment_is_protected():
    from app.domain.models import BlockType, LockedCommitment
    lock = LockedCommitment(
        commitment_id="L-001", section="B-C", line=Line.UP,
        start_time=datetime(2026, 8, 27, 2, tzinfo=timezone.utc),
        end_time=datetime(2026, 8, 27, 2, 30, tzinfo=timezone.utc),
        block_type=BlockType.FULL_BLOCK, description="Locked", locked=True,
    )
    result = CandidateGenerator().generate(dataset([task()], locks=[lock]))
    assert any(r.reason_code == "LOCKED_COMMITMENT_CONFLICT" for r in result.rejections)


def test_no_resource_makes_task_unschedulable():
    ds = dataset([task()])
    ds.resources = []
    result = CandidateGenerator().generate(ds)
    assert not result.candidates
    assert result.unschedulable_task_ids == ["T-001"]
