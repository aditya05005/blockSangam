from dataclasses import dataclass, field
from datetime import datetime

from app.domain.models import BlockType, Line


@dataclass(frozen=True)
class JointBlock:
    block_id: str
    section: str
    line: Line
    start_time: datetime
    end_time: datetime
    candidate_ids: tuple[str, ...]
    task_ids: tuple[str, ...]
    resource_ids: tuple[str, ...]
    block_type: BlockType = BlockType.FULL_BLOCK
    traffic_block: bool = False
    power_isolation: bool = False
    snt_disconnection: bool = False


@dataclass(frozen=True)
class BlockRejection:
    candidate_ids: tuple[str, ...]
    reason_code: str
    message: str


@dataclass
class BlockPlanningResult:
    joint_blocks: list[JointBlock] = field(default_factory=list)
    standalone_candidate_ids: list[str] = field(default_factory=list)
    rejections: list[BlockRejection] = field(default_factory=list)

    @property
    def block_count(self) -> int:
        return len(self.joint_blocks)
