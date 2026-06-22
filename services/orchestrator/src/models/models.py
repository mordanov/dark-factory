"""PostgreSQL ORM models.

jobs       — the async job queue (one row per ticket processing request)
audit_log  — immutable record of every orchestrator decision
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timezone

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.postgres import Base


def _now() -> datetime:
    return datetime.now(UTC)


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


# ---------------------------------------------------------------------------
# Job Queue
# ---------------------------------------------------------------------------

JOB_STATUS_ENUM = Enum(
    "pending",
    "running",
    "done",
    "failed",
    name="job_status",
)

JOB_TYPE_ENUM = Enum(
    "orchestrate",
    "distill",
    name="job_type",
)


class Job(Base):
    """One unit of async work in the orchestrator queue."""

    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    job_type: Mapped[str] = mapped_column(JOB_TYPE_ENUM, nullable=False)

    # Ticket Manager identifiers
    ticket_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    status: Mapped[str] = mapped_column(JOB_STATUS_ENUM, nullable=False, default="pending")
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Who triggered this job (user_id from JWT, or "system" for distiller)
    triggered_by: Mapped[str] = mapped_column(String(255), nullable=False, default="system")

    # Serialised input payload (event, ticket snapshot, etc.)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    # Result written on completion
    result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    audit_entries: Mapped[list[AuditLog]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )


# ---------------------------------------------------------------------------
# Audit Log
# ---------------------------------------------------------------------------


class AuditLog(Base):
    """Immutable log of every orchestrator decision."""

    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True
    )
    ticket_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(String(255), nullable=False)

    action: Mapped[str] = mapped_column(
        String(64), nullable=False
    )  # ADVANCE, BLOCK, ASSIGN, WAIT, …
    from_state: Mapped[str | None] = mapped_column(String(64))
    to_state: Mapped[str | None] = mapped_column(String(64))
    assigned_agent: Mapped[str | None] = mapped_column(String(64))
    blocked_reason: Mapped[str | None] = mapped_column(Text)
    override_logged: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    details: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # Full orchestrator decision JSON for traceability
    decision_payload: Mapped[dict | None] = mapped_column(JSONB)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    job: Mapped[Job | None] = relationship(back_populates="audit_entries")
