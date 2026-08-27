from pathlib import Path

from app.adapters.common import parse_bool, parse_datetime, read_csv
from app.domain.models import Department, Task, Line


TASK_COLUMNS = {
    "task_id", "department", "section", "line", "task_type",
    "duration_minutes", "earliest_start", "latest_finish", "criticality",
    "defect_severity", "asset_criticality", "failure_consequence",
    "deferral_history", "mandatory", "requires_traffic_block",
    "requires_power_isolation", "requires_snt_disconnection",
}


def load_tasks(path: str | Path, department: Department) -> tuple[list[Task], list[dict]]:
    df = read_csv(path, TASK_COLUMNS)
    tasks: list[Task] = []
    errors: list[dict] = []

    for row_number, row in df.iterrows():
        try:
            row_department = Department(str(row["department"]).strip().upper())
            if row_department != department:
                raise ValueError(f"Expected department {department.value}, got {row_department.value}")

            tasks.append(Task(
                task_id=str(row["task_id"]).strip(),
                department=row_department,
                section=str(row["section"]).strip(),
                line=Line(str(row["line"]).strip().upper()),
                task_type=str(row["task_type"]).strip(),
                duration_minutes=int(row["duration_minutes"]),
                earliest_start=parse_datetime(row["earliest_start"]),
                latest_finish=parse_datetime(row["latest_finish"]),
                criticality=int(row["criticality"]),
                defect_severity=int(row["defect_severity"]),
                asset_criticality=int(row["asset_criticality"]),
                failure_consequence=int(row["failure_consequence"]),
                deferral_history=int(row["deferral_history"]),
                mandatory=parse_bool(row["mandatory"]),
                requires_traffic_block=parse_bool(row["requires_traffic_block"]),
                requires_power_isolation=parse_bool(row["requires_power_isolation"]),
                requires_snt_disconnection=parse_bool(row["requires_snt_disconnection"]),
                restoration_minutes=int(row.get("restoration_minutes", 0)),
            ))
        except Exception as exc:
            errors.append({"source": department.value, "row": row_number + 2, "error": str(exc)})

    return tasks, errors


def load_tms_tasks(path: str | Path):
    return load_tasks(path, Department.ENGINEERING)


def load_smms_tasks(path: str | Path):
    return load_tasks(path, Department.SNT)


def load_tdms_tasks(path: str | Path):
    return load_tasks(path, Department.TRD)
