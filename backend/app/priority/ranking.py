from .engine import PriorityResult


def rank_priority_results(results: list[PriorityResult]) -> list[PriorityResult]:
    return sorted(
        results,
        key=lambda result: (
            not result.mandatory,
            -result.score,
            result.latest_finish,
            result.task_id,
        ),
    )
