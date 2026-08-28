from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from app.candidates import CandidateGenerator
from app.candidates.models import CandidateGenerationResult
from app.loaders import load_dataset
from app.pipeline import BlockSangamPipeline
from app.planning import explain_unscheduled
from app.scenarios import materialize_scenario, scenario_definition
from app.validation import ScheduleValidator
from fastapi.testclient import TestClient
from app.api import create_app


BASE_DIR = Path(__file__).resolve().parents[2] / "data" / "synthetic"


def run_scenario(name: str):
    definition = scenario_definition(name)
    with TemporaryDirectory(prefix=f"blocksangam-{name}-") as temporary:
        scenario_dir = materialize_scenario(name, Path(temporary) / "data", BASE_DIR)
        dataset = load_dataset(scenario_dir, goods_forecast=definition.forecast)
        result = BlockSangamPipeline(max_solve_time_seconds=2).run_dataset(dataset)
        candidates = CandidateGenerator().generate(dataset)
        # Return values are safe because all objects are in-memory; the temp
        # directory is only needed while adapters read the CSV fixtures.
        return dataset, result, candidates


def test_phase11_base_reference_is_valid_and_mandatory_tasks_are_handled():
    dataset, result, _ = run_scenario("base")

    assert not dataset.errors
    assert result.status in {"VALID_OPTIMAL", "VALID_FEASIBLE"}
    assert result.validation.valid
    assert result.schedule.status.value in {"OPTIMAL", "FEASIBLE"}
    selected_task_ids = {candidate.task_id for candidate in result.schedule.selected_candidates}
    assert {task.task_id for task in dataset.tasks if task.mandatory} <= selected_task_ids


def test_phase11_missing_corridor_capacity_is_explained_as_no_candidate():
    dataset, result, candidates = run_scenario("missing_corridor")

    assert result.schedule.status.value == "INFEASIBLE"
    assert result.status == "INVALID"
    assert not any(candidate.task_id == "ENG-002" for candidate in candidates.candidates)
    assert any(rejection.task_id == "ENG-002" and rejection.reason_code == "NO_FEASIBLE_CANDIDATE" for rejection in candidates.rejections)
    assert "ENG-002" in result.schedule.unscheduled_mandatory_task_ids
    explanation = next(item for item in explain_unscheduled(dataset, candidates, result.schedule.selected_candidates) if item["task_id"] == "ENG-002")
    assert explanation["candidate_state"] == "NO_CANDIDATES_GENERATED"


def test_phase11_unavailable_resource_rejects_candidates_without_fabrication():
    _, result, candidates = run_scenario("resource_unavailable")

    assert result.schedule.status.value == "INFEASIBLE"
    assert not any(candidate.task_id.startswith("ENG-") for candidate in candidates.candidates)
    assert any(rejection.reason_code == "RESOURCE_UNAVAILABLE" for rejection in candidates.rejections)
    assert "ENG-001" in result.schedule.unscheduled_mandatory_task_ids


def test_phase11_locked_commitment_is_preserved_and_task_can_move():
    dataset, result, candidates = run_scenario("locked_commitment")

    assert result.status in {"VALID_OPTIMAL", "VALID_FEASIBLE"}
    lock = next(lock for lock in dataset.locked_commitments if lock.commitment_id == "SCN-LOCK-ENG002")
    for candidate in result.schedule.selected_candidates:
        assert not (
            candidate.section == lock.section
            and candidate.line == lock.line
            and candidate.start_time < lock.end_time
            and lock.start_time < candidate.end_time
        )
    selected = next(candidate for candidate in result.schedule.selected_candidates if candidate.task_id == "ENG-002")
    assert selected.start_time.hour == 3
    assert any(rejection.reason_code == "LOCKED_COMMITMENT_CONFLICT" for rejection in candidates.rejections)


def test_phase11_stressed_goods_forecast_is_processed_honestly():
    base_dataset, base_result, _ = run_scenario("base")
    stressed_dataset, stressed_result, _ = run_scenario("stressed_goods")

    assert len(stressed_dataset.goods_movements) > len(base_dataset.goods_movements)
    assert stressed_result.status in {"VALID_OPTIMAL", "VALID_FEASIBLE", "INVALID"}
    assert stressed_result.schedule.status.value in {"OPTIMAL", "FEASIBLE", "INFEASIBLE", "UNKNOWN"}
    if stressed_result.status in {"VALID_OPTIMAL", "VALID_FEASIBLE"}:
        assert stressed_result.validation.valid
    assert stressed_result.statistics.candidates_generated >= 0
    assert stressed_result.statistics.total_time_seconds >= 0
    assert base_result.statistics.tasks_considered == stressed_result.statistics.tasks_considered


def test_phase11_competing_maintenance_preserves_hard_constraints():
    dataset, result, _ = run_scenario("competing_maintenance")

    assert result.status in {"VALID_OPTIMAL", "VALID_FEASIBLE"}
    assert result.validation.valid
    selected = result.schedule.selected_candidates
    mandatory_ids = {task.task_id for task in dataset.tasks if task.mandatory}
    assert mandatory_ids <= {candidate.task_id for candidate in selected}
    for index, left in enumerate(selected):
        for right in selected[index + 1 :]:
            overlaps = left.start_time < right.end_time and right.start_time < left.end_time
            same_corridor = left.section == right.section and left.line == right.line
            shared_resource = bool(set(left.resource_ids) & set(right.resource_ids))
            assert not (overlaps and (same_corridor or shared_resource))


def test_phase11_explanation_distinguishes_optimizer_rejection():
    dataset, result, candidates = run_scenario("base")
    explanations = explain_unscheduled(dataset, candidates, result.schedule.selected_candidates)

    optional_optimizer_rejection = next(item for item in explanations if item["task_id"] == "SNT-003")
    assert optional_optimizer_rejection["candidate_state"] == "CANDIDATES_EXISTED"
    assert optional_optimizer_rejection["reason_code"] == "OPTIMIZER_NOT_SELECTED"


def test_phase11_independent_validator_rejects_corrupted_plan_without_repairing():
    dataset, result, _ = run_scenario("base")
    target = next(candidate for candidate in result.schedule.selected_candidates if candidate.task_id == "ENG-002")
    corrupted = replace(target, start_time=target.start_time - timedelta(minutes=30), end_time=target.end_time - timedelta(minutes=30))
    corrupted_candidates = CandidateGenerationResult(
        candidates=[corrupted if candidate.candidate_id == target.candidate_id else candidate for candidate in result.schedule.selected_candidates],
        rejections=[],
    )

    validation = ScheduleValidator().validate(dataset, result.blocks, corrupted_candidates)

    assert not validation.valid
    assert any(issue.code == "TRAIN_MOVEMENT_CONFLICT" for issue in validation.errors)
    corrupted_target = next(candidate for candidate in corrupted_candidates.candidates if candidate.candidate_id == target.candidate_id)
    assert corrupted_target != target


def test_phase11_scenario_catalog_is_deterministic_and_complete():
    expected = {"base", "missing_corridor", "resource_unavailable", "locked_commitment", "stressed_goods", "competing_maintenance"}
    from app.scenarios import available_scenarios

    assert {item["name"] for item in available_scenarios()} == expected


def test_phase11_api_exposes_scenarios_and_preserves_infeasible_status():
    api = TestClient(create_app("sqlite://"))
    catalog = api.get("/api/scenarios")
    assert catalog.status_code == 200
    assert {item["name"] for item in catalog.json()["scenarios"]} == {
        "base", "missing_corridor", "resource_unavailable", "locked_commitment", "stressed_goods", "competing_maintenance",
    }

    response = api.post("/api/schedule", json={"scenario": "missing_corridor", "max_solve_time": 1})
    assert response.status_code == 200
    body = response.json()
    assert body["scenario"] == "missing_corridor"
    assert body["solver"]["status"] == "INFEASIBLE"
    assert body["validation_status"] == "INVALID"
    assert any(item["task_id"] == "ENG-002" for item in body["unscheduled"])
