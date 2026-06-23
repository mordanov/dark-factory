"""ORM models for Agent Dispatcher."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.session import Base


def _now() -> datetime:
    return datetime.now(UTC)


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


AGENT_RUN_STATUS_ENUM = Enum(
    "pending",
    "running",
    "completed",
    "needs_review",
    "failed",
    "timed_out",
    name="agent_run_status",
    create_type=False,
)


class BrainstormSession(Base):
    __tablename__ = "brainstorm_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    ticket_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    project_name: Mapped[str] = mapped_column(String(255), nullable=False)
    current_round: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    max_rounds: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="active")
    consensus: Mapped[str | None] = mapped_column(String(50), nullable=True)
    concluded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )

    runs: Mapped[list[AgentRun]] = relationship(
        "AgentRun", back_populates="brainstorm_session", lazy="select"
    )


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    ticket_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(String(255), nullable=False)
    agent_id: Mapped[str] = mapped_column(String(255), nullable=False)
    runner_mode: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(AGENT_RUN_STATUS_ENUM, nullable=False, default="pending")
    round_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    brainstorm_session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("brainstorm_sessions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    context_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    raw_output: Mapped[str | None] = mapped_column(Text, nullable=True)
    result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )

    brainstorm_session: Mapped[BrainstormSession | None] = relationship(
        "BrainstormSession", back_populates="runs", lazy="select"
    )
