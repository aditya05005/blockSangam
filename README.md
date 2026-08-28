# BlockSangam Phase 10

BlockSangam is a local, synthetic-data prototype for constraint-checked railway maintenance block planning. It is advisory only and does not issue operational railway blocks.

## Start the backend

From the repository root:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
$env:PYTHONPATH = "."
uvicorn app.api.main:app --reload
```

The API is available at `http://127.0.0.1:8000`; interactive documentation is at `/docs`.

## Start the dashboard

In a second terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open `http://127.0.0.1:5173`. The Vite development proxy forwards `/api` requests to the backend.

The dashboard can generate the base or stressed synthetic goods forecast, display summary counts, schedule entries, a corridor timeline, task details, independent validation issues, unscheduled explanations, and download the actual API response as JSON.

## Generate a schedule from the CLI

```powershell
cd backend
$env:PYTHONPATH = "."
python -m app.cli
```

The CLI writes `output/schedule.json`.

The direct API endpoint is `POST /api/schedule`:

```json
{
  "goods_forecast": "base",
  "max_solve_time": 10
}
```

It also accepts `data_dir` for another local synthetic-data directory. The endpoint calls the existing `BlockSangamPipeline`; scheduling decisions do not run in the frontend.

## Result statuses

- `VALID_OPTIMAL`: the solver proved an optimal result and the independent validator found no errors.
- `VALID_FEASIBLE`: the solver found a valid result within its time limit.
- `INVALID`: the generated result contains independent-validator errors; it must not be treated as an approved plan.
- `INFEASIBLE`: the solver could not satisfy the hard scheduling constraints. The response includes the solver message and any unscheduled mandatory task IDs.

The Phase 10 API also provides snapshot-backed endpoints for plan review, metrics, replanning, controlled review status, and JSON/CSV export. SQLite is used locally at `backend/block_sangam.db`.

## Tests

```powershell
cd backend
$env:PYTHONPATH = "."
pytest -q

cd ..\frontend
npm run build
```
