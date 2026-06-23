"""Pydantic v2 schemas — request/response DTOs.

Schemas are grouped by domain.  Each domain has:
  Base  – shared fields
  Create / Update – input schemas (strict)
  Response – output schema (from_attributes = True)

This mirrors the standard FastAPI convention and avoids leaking ORM
internals to the HTTP layer (SOLID / SRP).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

# ---------------------------------------------------------------------------
# Shared
# ---------------------------------------------------------------------------


class OrmModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------


class UserBase(BaseModel):
    email: EmailStr
    full_name: str = Field(default="", max_length=255)
    is_admin: bool = Field(default=False)


class UserCreate(UserBase):
    password: str = Field(min_length=8, max_length=128)


class UserUpdate(BaseModel):
    email: EmailStr | None = None
    full_name: str | None = Field(default=None, max_length=255)
    is_admin: bool | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=8, max_length=128)


class UserResponse(OrmModel):
    id: uuid.UUID
    email: str
    full_name: str
    is_admin: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime


class UserListResponse(BaseModel):
    items: list[UserResponse]
    total: int


# ---------------------------------------------------------------------------
# Ticket-manager context
# ---------------------------------------------------------------------------


class TmProject(BaseModel):
    """Lightweight project representation from Ticket Manager."""

    id: str
    name: str
    description: str | None = None


class TmTicket(BaseModel):
    """Lightweight ticket representation from Ticket Manager."""

    id: str
    title: str
    description: str | None = None
    status: str | None = None
    type: str | None = None


# ---------------------------------------------------------------------------
# Prompt Sessions
# ---------------------------------------------------------------------------


class SessionCreate(BaseModel):
    session_type: Literal["new_project", "existing_project"]
    # Required when session_type == "existing_project"
    tm_project_id: str | None = None
    # Required when session_type == "new_project"
    tm_project_name: str | None = Field(default=None, max_length=255)
    # Initial prompt text from the user
    initial_prompt: str = Field(min_length=1)

    @field_validator("tm_project_id")
    @classmethod
    def validate_project_id(cls, v, info):
        if info.data.get("session_type") == "existing_project" and not v:
            raise ValueError("tm_project_id is required for existing_project")
        return v

    @field_validator("tm_project_name")
    @classmethod
    def validate_project_name(cls, v, info):
        if info.data.get("session_type") == "new_project" and not v:
            raise ValueError("tm_project_name is required for new_project")
        return v


class SessionResponse(OrmModel):
    id: uuid.UUID
    session_type: str
    tm_project_id: str | None
    tm_project_name: str | None
    tm_ticket_id: str | None
    tm_ticket_title: str | None
    status: str
    created_at: datetime
    updated_at: datetime


class SessionListResponse(BaseModel):
    items: list[SessionResponse]
    total: int


# ---------------------------------------------------------------------------
# Prompt Iterations
# ---------------------------------------------------------------------------


class IterationResponse(OrmModel):
    id: uuid.UUID
    session_id: uuid.UUID
    iteration_number: int
    role: str
    prompt_text: str
    llm_assessment: str | None
    llm_questions: str | None
    llm_suggested_title: str | None
    user_comment: str | None
    is_approved: bool | None
    created_at: datetime


class UserFeedback(BaseModel):
    """User response to an assistant iteration."""

    is_approved: bool
    comment: str | None = Field(default=None, max_length=2000)


class RevertRequest(BaseModel):
    """Roll back to a specific iteration number."""

    target_iteration_number: int = Field(ge=1)


# ---------------------------------------------------------------------------
# Approval / Ticket creation
# ---------------------------------------------------------------------------


class ApproveRequest(BaseModel):
    """Payload to finalise a session and create a ticket."""

    ticket_title: str = Field(min_length=1, max_length=500)
    # For new projects only
    project_description: str | None = Field(default=None, max_length=2000)


# ---------------------------------------------------------------------------
# Planning Agent — Plan tree nodes
# ---------------------------------------------------------------------------


class PlanTask(BaseModel):
    local_id: str = Field(pattern=r"^task-\d+-\d+$")
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(max_length=500)
    ticket_type: Literal["task", "implementation", "investigation"] = "task"
    complexity: Literal["S", "M", "L", "XL"] = "M"
    depends_on: list[str] = Field(default_factory=list)


class PlanStory(BaseModel):
    local_id: str = Field(pattern=r"^story-\d+$")
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(max_length=500)
    ticket_type: Literal["story"] = "story"
    tasks: list[PlanTask] = Field(default_factory=list, max_length=10)


class PlanEpic(BaseModel):
    local_id: Literal["epic-1"] = "epic-1"
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(max_length=500)
    ticket_type: Literal["epic"] = "epic"


class PlanContent(BaseModel):
    epic: PlanEpic
    stories: list[PlanStory] = Field(min_length=1, max_length=10)


# ---------------------------------------------------------------------------
# Planning Agent — Agent configuration
# ---------------------------------------------------------------------------


class AgentOverride(BaseModel):
    agent_id: str
    override_text: str = Field(max_length=2000)


class AgentConfig(BaseModel):
    project_id: str
    tech_stack: list[str] = Field(default_factory=list)
    agent_overrides: list[AgentOverride] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Planning Agent — API DTOs
# ---------------------------------------------------------------------------


class PlanResponse(OrmModel):
    id: uuid.UUID
    session_id: uuid.UUID
    status: str
    plan_content: dict | None = None
    agent_config: dict | None = None
    validation_errors: list[str] | None = None
    created_ticket_ids: list[str] | None = None
    ticket_id_map: dict | None = None
    tm_epic_id: str | None = None
    created_at: datetime
    updated_at: datetime


class PlanUpdateRequest(BaseModel):
    plan_content: dict


class PlanStatusResponse(BaseModel):
    status: str
    created_count: int
    total: int
    errors: list[str] = Field(default_factory=list)


class PlanGenerateResponse(BaseModel):
    session_id: uuid.UUID
    plan_id: uuid.UUID
    status: str


class PlanConfirmResponse(BaseModel):
    session_id: uuid.UUID
    plan_id: uuid.UUID
    status: str
