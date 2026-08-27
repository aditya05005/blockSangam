import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from app.pipeline.models import PipelineResult


def _json_default(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "value"):
        return value.value
    if hasattr(value, "__dict__"):
        return value.__dict__
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def to_dict(result: PipelineResult) -> dict:
    return {
        "schema_version": "1.0",
        "status": result.status,
        "summary": {
            "tasks_considered": result.statistics.tasks_considered,
            "tasks_scheduled": result.statistics.tasks_scheduled,
            "candidates_generated": result.statistics.candidates_generated,
            "candidates_selected": result.statistics.candidates_selected,
            "joint_blocks": result.statistics.joint_blocks,
            "total_time_seconds": round(result.statistics.total_time_seconds, 6),
        },
        "blocks": [
            {
                "block_id": block.block_id,
                "section": block.section,
                "line": block.line.value,
                "start_time": block.start_time.isoformat(),
                "end_time": block.end_time.isoformat(),
                "candidate_ids": list(block.candidate_ids),
                "task_ids": list(block.task_ids),
                "resource_ids": list(block.resource_ids),
                "block_type": block.block_type.value,
                "traffic_block": block.traffic_block,
                "power_isolation": block.power_isolation,
                "snt_disconnection": block.snt_disconnection,
            }
            for block in result.blocks.joint_blocks
        ],
        "validation": {
            "valid": result.validation.valid,
            "errors": [asdict(issue) for issue in result.validation.errors],
            "warnings": [asdict(issue) for issue in result.validation.warnings],
            "checked_tasks": result.validation.checked_tasks,
            "checked_blocks": result.validation.checked_blocks,
        },
    }


def write_json(result: PipelineResult, output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(to_dict(result), indent=2, default=_json_default) + "\n", encoding="utf-8")
    return path
