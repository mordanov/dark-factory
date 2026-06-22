"""ORM models.

Keeping all models in one file avoids circular imports while staying small
enough to reason about easily (KISS).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.session import Base


def _now() -> datetime:
    return datetime.now(UTC)


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    sessions: Mapped[list[PromptSession]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    __table_args__ = (UniqueConstraint("email", name="uq_users_email"),)


# ---------------------------------------------------------------------------
# Prompt Sessions
# ---------------------------------------------------------------------------


class SessionStatus(str):
    IN_PROGRESS = "in_progress"
    APPROVED = "approved"
    CANCELLED = "cancelled"


SESSION_STATUS_ENUM = Enum(
    "in_progress",
    "approved",
    "cancelled",
    name="session_status",
    create_type=False,
)

SESSION_TYPE_ENUM = Enum("new_project", "existing_project", name="session_type", create_type=False)


class PromptSession(Base):
    """One user's work-session refining a prompt for a project."""

    __tablename__ = "prompt_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

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

    user: Mapped[User] = relationship(back_populates="sessions")
    iterations: Mapped[list[PromptIteration]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="PromptIteration.iteration_number",
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
