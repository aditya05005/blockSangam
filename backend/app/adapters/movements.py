from pathlib import Path

from app.adapters.common import parse_datetime, parse_optional_text, read_csv
from app.domain.models import Line, MovementType, TrainMovement

TIMETABLE_COLUMNS = {"movement_id", "movement_type", "section", "line", "start_time", "end_time", "service_name", "priority"}
GOODS_COLUMNS = {"movement_id", "movement_type", "section", "line", "start_time", "end_time", "confidence", "forecast_version"}


def _load_movements(path: str | Path, required: set[str], expected_type: MovementType, source: str) -> tuple[list[TrainMovement], list[dict]]:
    df = read_csv(path, required)
    items, errors = [], []
    for row_number, row in df.iterrows():
        try:
            movement_type = MovementType(str(row["movement_type"]).strip().upper())
            if movement_type != expected_type:
                raise ValueError(f"Expected movement_type={expected_type.value}, got {movement_type.value}")
            items.append(TrainMovement(
                movement_id=str(row["movement_id"]).strip(),
                movement_type=movement_type,
                section=str(row["section"]).strip(),
                line=Line(str(row["line"]).strip().upper()),
                start_time=parse_datetime(row["start_time"]),
                end_time=parse_datetime(row["end_time"]),
                service_name=parse_optional_text(row["service_name"]) if "service_name" in row else None,
                priority=int(row["priority"]) if "priority" in row and str(row["priority"]).strip() else None,
                confidence=float(row["confidence"]) if "confidence" in row and str(row["confidence"]).strip() else None,
                forecast_version=parse_optional_text(row["forecast_version"]) if "forecast_version" in row else None,
            ))
        except Exception as exc:
            errors.append({"source": source, "row": row_number + 2, "error": str(exc)})
    return items, errors


def load_timetable(path: str | Path):
    return _load_movements(path, TIMETABLE_COLUMNS, MovementType.PASSENGER, "TIMETABLE")


def load_goods_forecast(path: str | Path):
    return _load_movements(path, GOODS_COLUMNS, MovementType.GOODS, "GOODS_FORECAST")
