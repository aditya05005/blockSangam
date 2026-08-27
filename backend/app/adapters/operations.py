from pathlib import Path

from app.adapters.common import parse_bool, parse_datetime, parse_optional_text, read_csv
from app.domain.models import BlockType, CorridorSlot, Department, Line, LockedCommitment, Resource, ResourceType


SLOT_COLUMNS = {"slot_id", "section", "line", "start_time", "end_time", "block_type", "traffic_block", "power_isolation", "snt_disconnection"}
RESOURCE_COLUMNS = {"resource_id", "department", "resource_type", "resource_name", "start_time", "end_time", "capacity"}
LOCK_COLUMNS = {"commitment_id", "section", "line", "start_time", "end_time", "block_type", "description", "locked"}


def load_corridor_slots(path: str | Path) -> tuple[list[CorridorSlot], list[dict]]:
    df = read_csv(path, SLOT_COLUMNS)
    items, errors = [], []
    for row_number, row in df.iterrows():
        try:
            items.append(CorridorSlot(
                slot_id=str(row["slot_id"]).strip(),
                section=str(row["section"]).strip(),
                line=Line(str(row["line"]).strip().upper()),
                start_time=parse_datetime(row["start_time"]),
                end_time=parse_datetime(row["end_time"]),
                block_type=BlockType(str(row["block_type"]).strip().upper()),
                traffic_block=parse_bool(row["traffic_block"]),
                power_isolation=parse_bool(row["power_isolation"]),
                snt_disconnection=parse_bool(row["snt_disconnection"]),
            ))
        except Exception as exc:
            errors.append({"source": "CORRIDOR_SLOTS", "row": row_number + 2, "error": str(exc)})
    return items, errors


def load_resources(path: str | Path) -> tuple[list[Resource], list[dict]]:
    df = read_csv(path, RESOURCE_COLUMNS)
    items, errors = [], []
    for row_number, row in df.iterrows():
        try:
            items.append(Resource(
                resource_id=str(row["resource_id"]).strip(),
                department=Department(str(row["department"]).strip().upper()),
                resource_type=ResourceType(str(row["resource_type"]).strip().upper()),
                resource_name=str(row["resource_name"]).strip(),
                start_time=parse_datetime(row["start_time"]),
                end_time=parse_datetime(row["end_time"]),
                capacity=int(row["capacity"]),
            ))
        except Exception as exc:
            errors.append({"source": "RESOURCES", "row": row_number + 2, "error": str(exc)})
    return items, errors


def load_locked_commitments(path: str | Path) -> tuple[list[LockedCommitment], list[dict]]:
    df = read_csv(path, LOCK_COLUMNS)
    items, errors = [], []
    for row_number, row in df.iterrows():
        try:
            items.append(LockedCommitment(
                commitment_id=str(row["commitment_id"]).strip(),
                section=str(row["section"]).strip(),
                line=Line(str(row["line"]).strip().upper()),
                start_time=parse_datetime(row["start_time"]),
                end_time=parse_datetime(row["end_time"]),
                block_type=BlockType(str(row["block_type"]).strip().upper()),
                description=str(row["description"]).strip(),
                locked=parse_bool(row["locked"]),
            ))
        except Exception as exc:
            errors.append({"source": "LOCKED_COMMITMENTS", "row": row_number + 2, "error": str(exc)})
    return items, errors
