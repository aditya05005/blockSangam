from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, model_validator


class Department(str, Enum):
    ENGINEERING = "ENGINEERING"
    SNT = "SNT"
    TRD = "TRD"


class Line(str, Enum):
    UP = "UP"
    DOWN = "DOWN"


class BlockType(str, Enum):
    FULL_BLOCK = "FULL_BLOCK"


class MovementType(str, Enum):
    PASSENGER = "PASSENGER"
    GOODS = "GOODS"


class ResourceType(str, Enum):
    TEAM = "TEAM"
    MACHINE = "MACHINE"


class Task(BaseModel):
    task_id: str = Field(min_length=1)
    department: Department
    section: str = Field(min_length=1)
    line: Line
    task_type: str = Field(min_length=1)
    duration_minutes: int = Field(gt=0)
    earliest_start: datetime
    latest_finish: datetime
    criticality: int = Field(ge=1, le=5)
    defect_severity: int = Field(ge=1, le=5)
    asset_criticality: int = Field(ge=1, le=5)
    failure_consequence: int = Field(ge=1, le=5)
    deferral_history: int = Field(ge=0)
    mandatory: bool
    requires_traffic_block: bool
    requires_power_isolation: bool
    requires_snt_disconnection: bool
    restoration_minutes: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_window(self):
        if self.latest_finish <= self.earliest_start:
            raise ValueError("latest_finish must be after earliest_start")
        return self


class CorridorSlot(BaseModel):
    slot_id: str = Field(min_length=1)
    section: str = Field(min_length=1)
    line: Line
    start_time: datetime
    end_time: datetime
    block_type: BlockType
    traffic_block: bool
    power_isolation: bool
    snt_disconnection: bool

    @model_validator(mode="after")
    def validate_window(self):
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        return self


class TrainMovement(BaseModel):
    movement_id: str = Field(min_length=1)
    movement_type: MovementType
    section: str = Field(min_length=1)
    line: Line
    start_time: datetime
    end_time: datetime
    service_name: str | None = None
    priority: int | None = Field(default=None, ge=1, le=5)
    confidence: float | None = Field(default=None, ge=0, le=1)
    forecast_version: str | None = None

    @model_validator(mode="after")
    def validate_window(self):
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        return self


class Resource(BaseModel):
    resource_id: str = Field(min_length=1)
    department: Department
    resource_type: ResourceType
    resource_name: str = Field(min_length=1)
    start_time: datetime
    end_time: datetime
    capacity: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_window(self):
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        return self


class LockedCommitment(BaseModel):
    commitment_id: str = Field(min_length=1)
    section: str = Field(min_length=1)
    line: Line
    start_time: datetime
    end_time: datetime
    block_type: BlockType
    description: str = Field(min_length=1)
    locked: bool = True

    @model_validator(mode="after")
    def validate_window(self):
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        return self
