"""ORM models.

Keeping all models in one file avoids circular imports while staying small
enough to reason about easily (KISS).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.session import Base


def _now() -> datetime:
    return datetime.now(UTC)


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


# ---------------------------------------------------------------------------
# Prompt Sessions
# ---------------------------------------------------------------------------


class SessionStatus(str):
    IN_PROGRESS = "in_progress"
    APPROVED = "approved"
    CANCELLED = "cancelled"
    PLANNING = "planning"
    PLAN_READY = "plan_ready"
    PLAN_CONFIRMED = "plan_confirmed"
    TICKETS_CREATED = "tickets_created"


SESSION_STATUS_ENUM = Enum(
    "in_progress",
    "approved",
    "cancelled",
    "planning",
    "plan_ready",
    "plan_confirmed",
    "tickets_created",
    name="session_status",
    create_type=False,
)


PLAN_STATUS_ENUM = Enum(
    "draft",
    "ready",
    "confirmed",
    "tickets_created",
    "error",
    name="plan_status",
    create_type=False,
)

SESSION_TYPE_ENUM = Enum("new_project", "existing_project", name="session_type", create_type=False)


class PromptSession(Base):
    """One user's work-session refining a prompt for a project."""

    __tablename__ = "prompt_sessions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(Text, nullable=False)

    # ticket-manager context
    session_type: Mapped[str] = mapped_column(SESSION_TYPE_ENUM, nullable=False)
    tm_project_id: Mapped[str | None] = mapped_column(
        String(255)
    )  # null for new projects until approved
    tm_project_name: Mapped[str | None] = mapped_column(
        String(255)
    )  # stored for new projects before creation
    tm_ticket_id: Mapped[str | None] = mapped_column(String(255))  # filled after approval
    tm_ticket_title: Mapped[str | None] = mapped_column(String(500))  # LLM-suggested, user-editable

    status: Mapped[str] = mapped_column(SESSION_STATUS_ENUM, nullable=False, default="in_progress")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    iterations: Mapped[list[PromptIteration]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="PromptIteration.iteration_number",
    )
    plan: Mapped[PromptPlan | None] = relationship(
        back_populates="session", uselist=False, cascade="all, delete-orphan"
    )


# ---------------------------------------------------------------------------
# Prompt Iterations
# ---------------------------------------------------------------------------


class IterationRole(str):
    USER = "user"
    ASSISTANT = "assistant"


ITERATION_ROLE_ENUM = Enum("user", "assistant", name="iteration_role", create_type=False)


class PromptIteration(Base):
    """One iteration within a PromptSession."""

    __tablename__ = "prompt_iterations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("prompt_sessions.id", ondelete="CASCADE"), nullable=False
    )
    iteration_number: Mapped[int] = mapped_column(Integer, nullable=False)

    # The refined prompt text for this iteration (assistant) or user input (user)
    role: Mapped[str] = mapped_column(ITERATION_ROLE_ENUM, nullable=False)
    prompt_text: Mapped[str] = mapped_column(Text, nullable=False)

    # LLM assessment / clarifying questions (only for assistant iterations)
    llm_assessment: Mapped[str | None] = mapped_column(Text)
    llm_questions: Mapped[str | None] = mapped_column(Text)  # clarifying questions if any
    llm_suggested_title: Mapped[str | None] = mapped_column(String(500))

    # User feedback on this iteration (filled by user before moving to next)
    user_comment: Mapped[str | None] = mapped_column(Text)  # "improve X"
    is_approved: Mapped[bool | None] = mapped_column(Boolean)  # null = pending

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    session: Mapped[PromptSession] = relationship(back_populates="iterations")


# ---------------------------------------------------------------------------
# Prompt Plans
# ---------------------------------------------------------------------------


class PromptPlan(Base):
    """Work breakdown plan generated from an approved prompt session."""

    __tablename__ = "prompt_plans"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("prompt_sessions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    status: Mapped[str] = mapped_column(PLAN_STATUS_ENUM, nullable=False, default="draft")
    plan_content: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    agent_config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    validation_errors: Mapped[list | None] = mapped_column(JSON, nullable=True)
    created_ticket_ids: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    ticket_id_map: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    tm_epic_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    session: Mapped[PromptSession] = relationship(back_populates="plan")
