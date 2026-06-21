"""ORM models — local copies of Orchestrator's jobs + audit_log tables.

These mirror ../orchestrator/src/models/models.py exactly.
ContextDistiller reads and updates these tables but never owns their schema.
"""
from __future__ import annotations
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.postgres import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


JOB_STATUS_ENUM = Enum(
    "pending", "running", "done", "failed",
    name="job_status",
)

JOB_TYPE_ENUM = Enum(
    "orchestrate", "distill",
    name="job_type",
)


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    job_type: Mapped[str] = mapped_column(JOB_TYPE_ENUM, nullable=False)
    ticket_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    status: Mapped[str] = mapped_column(JOB_STATUS_ENUM, nullable=False, default="pending")
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    triggered_by: Mapped[str] = mapped_column(String(255), nullable=False, default="system")
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    audit_entries: Mapped[list[AuditLog]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True
    )
    ticket_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(String(255), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    from_state: Mapped[str | None] = mapped_column(String(64))
    to_state: Mapped[str | None] = mapped_column(String(64))
    assigned_agent: Mapped[str | None] = mapped_column(String(64))
    blocked_reason: Mapped[str | None] = mapped_column(Text)
    override_logged: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    details: Mapped[str] = mapped_column(Text, nullable=False, default="")
    decision_payload: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    job: Mapped[Job | None] = relationship(back_populates="audit_entries")
