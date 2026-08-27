import argparse
from pathlib import Path

from app.output import write_json
from app.pipeline import BlockSangamPipeline


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the BlockSangam scheduling pipeline")
    project_root = Path(__file__).resolve().parents[2]
    parser.add_argument("--data-dir", default=str(project_root / "data" / "synthetic"))
    parser.add_argument("--forecast", default="base")
    parser.add_argument("--output", default=str(project_root / "output" / "schedule.json"))
    parser.add_argument("--max-solve-time", type=float, default=10.0)
    args = parser.parse_args()

    print("BlockSangam - end-to-end scheduling pipeline")
    result = BlockSangamPipeline(max_solve_time_seconds=args.max_solve_time).run(
        args.data_dir, goods_forecast=args.forecast
    )
    path = write_json(result, args.output)

    print(f"Status            : {result.status}")
    print(f"Tasks scheduled   : {result.statistics.tasks_scheduled}/{result.statistics.tasks_considered}")
    print(f"Candidates        : {result.statistics.candidates_selected}/{result.statistics.candidates_generated}")
    print(f"Joint blocks      : {result.statistics.joint_blocks}")
    print(f"Validation        : {'VALID' if result.validation.valid else 'INVALID'}")
    print(f"Output            : {path}")

    return 0 if result.validation.valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
