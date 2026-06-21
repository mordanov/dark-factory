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
    email: Optional[EmailStr] = None
    full_name: Optional[str] = Field(default=None, max_length=255)
    is_admin: Optional[bool] = None
    is_active: Optional[bool] = None
    password: Optional[str] = Field(default=None, min_length=8, max_length=128)


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
    description: Optional[str] = None


class TmTicket(BaseModel):
    """Lightweight ticket representation from Ticket Manager."""
    id: str
    title: str
    description: Optional[str] = None
    status: Optional[str] = None
    type: Optional[str] = None


# ---------------------------------------------------------------------------
# Prompt Sessions
# ---------------------------------------------------------------------------

class SessionCreate(BaseModel):
    session_type: Literal["new_project", "existing_project"]
    # Required when session_type == "existing_project"
    tm_project_id: Optional[str] = None
    # Required when session_type == "new_project"
    tm_project_name: Optional[str] = Field(default=None, max_length=255)
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
    tm_project_id: Optional[str]
    tm_project_name: Optional[str]
    tm_ticket_id: Optional[str]
    tm_ticket_title: Optional[str]
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
    llm_assessment: Optional[str]
    llm_questions: Optional[str]
    llm_suggested_title: Optional[str]
    user_comment: Optional[str]
    is_approved: Optional[bool]
    created_at: datetime


class UserFeedback(BaseModel):
    """User response to an assistant iteration."""
    is_approved: bool
    comment: Optional[str] = Field(default=None, max_length=2000)


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
    project_description: Optional[str] = Field(default=None, max_length=2000)
