from fastapi.testclient import TestClient

from app.api import create_app
from app.database.models import Base


def client():
    return TestClient(create_app("sqlite://"))


def test_phase10_api_persists_snapshot_and_plan_flow():
    api = client()

    assert api.get("/api/health").json()["advisory_only"] is True
    assert api.post("/api/imports/validate").json()["valid"] is True

    snapshot_response = api.post("/api/snapshots")
    assert snapshot_response.status_code == 201
    snapshot = snapshot_response.json()
    assert snapshot["validation_status"] == "READY"
    assert snapshot["source_hashes"]["tms"].startswith("sha256:")

    plan_response = api.post(
        "/api/plans/run", json={"snapshot_id": snapshot["snapshot_id"], "max_solve_time": 1}
    )
    assert plan_response.status_code == 200
    plan = plan_response.json()
    plan_id = plan["plan_id"]
    assert plan["status"] == "PROPOSED"
    assert plan["solver_status"] in {"OPTIMAL", "FEASIBLE", "INFEASIBLE", "UNKNOWN"}
    assert "hard_constraint_violations" in plan["plan"]["metrics"]
    assert api.get(f"/api/plans/{plan_id}").status_code == 200
    assert api.get(f"/api/plans/{plan_id}/unscheduled").status_code == 200
    assert api.get(f"/api/plans/{plan_id}/metrics").json()["baseline_metrics"]
    assert api.get(f"/api/plans/{plan_id}/export?format=json").status_code == 200
    assert api.get(f"/api/plans/{plan_id}/export?format=csv").headers["content-type"].startswith("text/csv")


def test_phase10_direct_schedule_endpoint_uses_pipeline_result():
    api = client()

    response = api.post("/api/schedule", json={"goods_forecast": "base", "max_solve_time": 1})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] in {"VALID_OPTIMAL", "VALID_FEASIBLE", "INVALID"}
    assert body["solver"]["status"] in {"OPTIMAL", "FEASIBLE", "INFEASIBLE", "UNKNOWN"}
    assert body["summary"]["tasks_considered"] == 11
    assert body["summary"]["candidates_generated"] > 0
    assert isinstance(body["schedule_entries"], list)
    assert "errors" in body["validation"]


def test_phase10_replan_creates_new_version_and_uses_controlled_status():
    api = client()
    snapshot = api.post("/api/snapshots").json()
    plan = api.post(
        "/api/plans/run", json={"snapshot_id": snapshot["snapshot_id"], "max_solve_time": 1}
    ).json()

    replan = api.post(
        f"/api/plans/{plan['plan_id']}/replan",
        json={"forecast": "stressed", "max_solve_time": 1},
    )
    assert replan.status_code == 200
    new_plan = replan.json()
    assert new_plan["plan_id"] != plan["plan_id"]
    assert new_plan["plan"]["change_summary"]["previous_plan"] == plan["plan_id"]
    assert new_plan["plan"]["change_summary"]["locked_blocks_changed"] == 0

    status = api.patch(
        f"/api/plans/{new_plan['plan_id']}/status", json={"status": "UNDER_REVIEW"}
    )
    assert status.status_code == 200
    assert status.json()["status"] == "UNDER_REVIEW"
    assert api.patch(
        f"/api/plans/{new_plan['plan_id']}/status", json={"status": "NOT_A_STATUS"}
    ).status_code == 422


def test_phase10_declares_the_database_tables():
    expected = {
        "data_snapshots",
        "source_records",
        "import_errors",
        "maintenance_tasks",
        "corridor_slots",
        "train_movements",
        "resource_calendars",
        "existing_commitments",
        "plan_runs",
        "proposed_blocks",
        "work_packages",
        "unscheduled_tasks",
        "plan_metrics",
        "plan_events",
    }
    assert expected <= set(Base.metadata.tables)
