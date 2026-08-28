import hashlib
from pathlib import Path

from fastapi.testclient import TestClient

from app.api import create_app
from app.scenarios import execute_scenario, simulate_scenario


BASE_DIR = Path(__file__).resolve().parents[2] / "data" / "synthetic"


def fixture_hashes():
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in BASE_DIR.glob("*.csv")
    }


def test_simulation_isolated_and_repeatable():
    before = fixture_hashes()
    first = simulate_scenario("missing_corridor", BASE_DIR, max_solve_time_seconds=1)
    second = simulate_scenario("missing_corridor", BASE_DIR, max_solve_time_seconds=1)

    assert fixture_hashes() == before
    assert first["comparison"]["impact"]["candidate_delta"] == -1
    assert first["scenario_result"]["solver"]["status"] == "INFEASIBLE"
    assert first["comparison"]["impact"]["newly_unscheduled"] == second["comparison"]["impact"]["newly_unscheduled"]
    assert first["scenario_result"]["summary"]["candidates_generated"] == second["scenario_result"]["summary"]["candidates_generated"]


def test_scenario_comparison_is_derived_from_actual_assignments():
    result = simulate_scenario("locked_commitment", BASE_DIR, max_solve_time_seconds=1)
    impact = result["comparison"]["impact"]

    assert result["base"]["summary"]["tasks_scheduled"] == 9
    assert result["scenario_result"]["summary"]["tasks_scheduled"] == 9
    assert "ENG-002" in impact["tasks_moved"]
    assert impact["newly_unscheduled"] == []
    assert impact["status_changed"] is False


def test_all_runtime_scenarios_execute_through_pipeline():
    for scenario_id in ("resource_unavailable", "stressed_goods", "competing_maintenance", "corridor_closure"):
        execution = execute_scenario(scenario_id, BASE_DIR, max_solve_time_seconds=1)
        assert execution.result.schedule.status.value in {"OPTIMAL", "FEASIBLE", "INFEASIBLE", "UNKNOWN"}
        assert execution.result.validation is not None


def test_simulation_api_returns_base_scenario_and_impact():
    client = TestClient(create_app("sqlite://"))
    response = client.post("/api/scenarios/missing_corridor/simulate", json={"max_solve_time": 1})

    assert response.status_code == 200
    body = response.json()
    assert body["base"]["status"] == "VALID_OPTIMAL"
    assert body["scenario_result"]["scenario"]["id"] == "missing_corridor"
    assert body["comparison"]["impact"]["candidate_delta"] == -1
    assert "ENG-002" in body["comparison"]["impact"]["newly_unscheduled"]


def test_unknown_simulation_scenario_is_rejected():
    client = TestClient(create_app("sqlite://"))
    assert client.post("/api/scenarios/not-a-scenario/simulate").status_code == 422


def test_custom_simulation_validates_base_identifiers_and_keeps_snapshot_isolated():
    client = TestClient(create_app("sqlite://"))
    before = fixture_hashes()
    response = client.post("/api/scenarios/simulate", json={
        "remove_corridor_slot_ids": ["SLOT-004"],
        "unavailable_resource_ids": ["RES-ENG-01"],
        "corridor_closure": {"section": "B-C", "line": "UP", "start_time": "2026-08-28T02:00", "end_time": "2026-08-28T04:00"},
    })

    assert response.status_code == 200
    body = response.json()
    assert body["scenario_result"]["scenario"]["id"] == "custom"
    assert "remove corridor slot SLOT-004" in body["scenario_result"]["scenario"]["modifications"]
    assert fixture_hashes() == before
    assert client.post("/api/scenarios/simulate", json={"remove_corridor_slot_ids": ["NO-SUCH-SLOT"]}).status_code == 422
