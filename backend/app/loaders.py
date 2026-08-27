from dataclasses import dataclass
from pathlib import Path

from app.adapters import (
    load_corridor_slots,
    load_goods_forecast,
    load_locked_commitments,
    load_resources,
    load_smms_tasks,
    load_tdms_tasks,
    load_timetable,
    load_tms_tasks,
)
from app.domain.models import CorridorSlot, LockedCommitment, Resource, Task, TrainMovement


@dataclass
class CanonicalDataset:
    engineering_tasks: list[Task]
    snt_tasks: list[Task]
    trd_tasks: list[Task]
    passenger_movements: list[TrainMovement]
    goods_movements: list[TrainMovement]
    corridor_slots: list[CorridorSlot]
    resources: list[Resource]
    locked_commitments: list[LockedCommitment]
    errors: list[dict]

    @property
    def tasks(self) -> list[Task]:
        return self.engineering_tasks + self.snt_tasks + self.trd_tasks

    @property
    def movements(self) -> list[TrainMovement]:
        return self.passenger_movements + self.goods_movements


def load_dataset(data_dir: str | Path, goods_forecast: str = "base") -> CanonicalDataset:
    data_dir = Path(data_dir)
    errors: list[dict] = []

    eng, err = load_tms_tasks(data_dir / "tms_tasks.csv"); errors.extend(err)
    snt, err = load_smms_tasks(data_dir / "smms_tasks.csv"); errors.extend(err)
    trd, err = load_tdms_tasks(data_dir / "tdms_tasks.csv"); errors.extend(err)
    passenger, err = load_timetable(data_dir / "timetable_movements.csv"); errors.extend(err)

    forecast_file = f"goods_forecast_{goods_forecast}.csv"
    goods, err = load_goods_forecast(data_dir / forecast_file); errors.extend(err)
    slots, err = load_corridor_slots(data_dir / "corridor_slots.csv"); errors.extend(err)
    resources, err = load_resources(data_dir / "resource_calendar.csv"); errors.extend(err)
    locks, err = load_locked_commitments(data_dir / "locked_commitments.csv"); errors.extend(err)

    return CanonicalDataset(
        engineering_tasks=eng,
        snt_tasks=snt,
        trd_tasks=trd,
        passenger_movements=passenger,
        goods_movements=goods,
        corridor_slots=slots,
        resources=resources,
        locked_commitments=locks,
        errors=errors,
    )
