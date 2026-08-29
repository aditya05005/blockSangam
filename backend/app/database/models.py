from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from sqlalchemy import JSON, DateTime, Enum as SAEnum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class PlanStatus(str, Enum):
    PROPOSED = "PROPOSED"
    UNDER_REVIEW = "UNDER_REVIEW"
    APPROVED_FOR_DEMO = "APPROVED_FOR_DEMO"
    LOCKED = "LOCKED"
    REJECTED = "REJECTED"
    SUPERSEDED = "SUPERSEDED"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class DataSnapshot(Base):
    __tablename__ = "data_snapshots"

    snapshot_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    schema_version: Mapped[str] = mapped_column(String(20), default="1.0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    goods_forecast: Mapped[str] = mapped_column(String(40), default="base")
    data_dir: Mapped[str] = mapped_column(Text)
    validation_status: Mapped[str] = mapped_column(String(40))
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    warning_count: Mapped[int] = mapped_column(Integer, default=0)
    source_counts: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    source_hashes: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class SourceRecord(Base):
    __tablename__ = "source_records"

    record_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    snapshot_id: Mapped[str] = mapped_column(ForeignKey("data_snapshots.snapshot_id"), index=True)
    source_name: Mapped[str] = mapped_column(String(40))
    source_record_id: Mapped[str] = mapped_column(String(100))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class ImportErrorRecord(Base):
    __tablename__ = "import_errors"

    error_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    snapshot_id: Mapped[str] = mapped_column(ForeignKey("data_snapshots.snapshot_id"), index=True)
    source_name: Mapped[str] = mapped_column(String(40))
    row_reference: Mapped[str] = mapped_column(String(100))
    reason_code: Mapped[str] = mapped_column(String(80))
    message: Mapped[str] = mapped_column(Text)


class SnapshotEntity(Base):
    """Common durable representation for normalized entities.

    The dedicated tables below intentionally keep the schema simple for the
    offline prototype while retaining the immutable snapshot boundary.
    """

    __abstract__ = True
    entity_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    snapshot_id: Mapped[str] = mapped_column(ForeignKey("data_snapshots.snapshot_id"), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class MaintenanceTask(SnapshotEntity):
    __tablename__ = "maintenance_tasks"


class CorridorSlot(SnapshotEntity):
    __tablename__ = "corridor_slots"


class TrainMovement(SnapshotEntity):
    __tablename__ = "train_movements"


class ResourceCalendar(SnapshotEntity):
    __tablename__ = "resource_calendars"


class ExistingCommitment(SnapshotEntity):
    __tablename__ = "existing_commitments"


class PlanRun(Base):
    __tablename__ = "plan_runs"

    plan_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    snapshot_id: Mapped[str] = mapped_column(ForeignKey("data_snapshots.snapshot_id"), index=True)
    planning_mode: Mapped[str] = mapped_column(String(20), default="weekly")
    solver_status: Mapped[str] = mapped_column(String(30))
    status: Mapped[PlanStatus] = mapped_column(
        SAEnum(PlanStatus, name="plan_status", native_enum=False), default=PlanStatus.PROPOSED
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    configuration: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    source_hashes: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class ProposedBlock(Base):
    __tablename__ = "proposed_blocks"

    block_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_id: Mapped[str] = mapped_column(ForeignKey("plan_runs.plan_id"), index=True)
    external_block_id: Mapped[str] = mapped_column(String(100))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class WorkPackage(Base):
    __tablename__ = "work_packages"

    work_package_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_id: Mapped[str] = mapped_column(ForeignKey("plan_runs.plan_id"), index=True)
    task_id: Mapped[str] = mapped_column(String(100))
    block_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class UnscheduledTask(Base):
    __tablename__ = "unscheduled_tasks"

    unscheduled_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_id: Mapped[str] = mapped_column(ForeignKey("plan_runs.plan_id"), index=True)
    task_id: Mapped[str] = mapped_column(String(100))
    reason_code: Mapped[str] = mapped_column(String(80))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class PlanMetric(Base):
    __tablename__ = "plan_metrics"

    metric_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_id: Mapped[str] = mapped_column(ForeignKey("plan_runs.plan_id"), index=True)
    metric_name: Mapped[str] = mapped_column(String(80))
    metric_value: Mapped[float] = mapped_column()
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class PlanEvent(Base):
    __tablename__ = "plan_events"

    event_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_id: Mapped[str] = mapped_column(ForeignKey("plan_runs.plan_id"), index=True)
    event_type: Mapped[str] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class DepartmentFeedback(Base):
    __tablename__ = "department_feedback"

    feedback_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    sender_role: Mapped[str] = mapped_column(String(30), index=True)
    recipient_role: Mapped[str] = mapped_column(String(30), index=True)
    department: Mapped[str] = mapped_column(String(30), index=True)
    task_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    message: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="OPEN", index=True)
    parent_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
