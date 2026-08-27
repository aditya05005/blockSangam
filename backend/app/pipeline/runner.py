from time import monotonic

from app.loaders import load_dataset
from app.priority import PriorityEngine
from app.candidates import CandidateGenerator
from app.scheduler import CPSATScheduler
from app.blocks import JointBlockBuilder
from app.validation import ScheduleValidator
from .models import PipelineResult, PipelineStatistics


class BlockSangamPipeline:
    def __init__(self, *, max_solve_time_seconds: float = 10.0):
        self.priority_engine = PriorityEngine()
        self.candidate_generator = CandidateGenerator()
        self.scheduler = CPSATScheduler(self.priority_engine, max_solve_time_seconds)
        self.block_builder = JointBlockBuilder()
        self.validator = ScheduleValidator()

    def run(self, data_dir: str, *, goods_forecast: str = "base") -> PipelineResult:
        started = monotonic()
        dataset = load_dataset(data_dir, goods_forecast=goods_forecast)
        if dataset.errors:
            raise ValueError(f"Input dataset contains {len(dataset.errors)} error(s)")

        priorities = self.priority_engine.rank(dataset.tasks)
        # CandidateGenerator derives feasibility from the canonical dataset.
        # Priority results are retained for the scheduling objective; they are
        # intentionally not passed into candidate generation.
        candidates = self.candidate_generator.generate(dataset)
        schedule = self.scheduler.solve(dataset, candidates)

        selected = type(candidates)(
            candidates=list(schedule.selected_candidates),
            rejections=candidates.rejections,
        )
        blocks = self.block_builder.build(selected)
        validation = self.validator.validate(dataset, blocks, selected)

        if not validation.valid:
            status = "INVALID"
        elif schedule.status.value == "OPTIMAL":
            status = "VALID_OPTIMAL"
        else:
            status = "VALID_FEASIBLE"

        stats = PipelineStatistics(
            tasks_considered=len(dataset.tasks),
            tasks_scheduled=len(schedule.selected_candidates),
            candidates_generated=len(candidates.candidates),
            candidates_selected=len(schedule.selected_candidates),
            joint_blocks=len(blocks.joint_blocks),
            total_time_seconds=monotonic() - started,
        )
        return PipelineResult(status, schedule, blocks, validation, stats, dataset.errors)
