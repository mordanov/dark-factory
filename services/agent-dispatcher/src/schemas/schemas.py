"""Pydantic schemas for Agent Dispatcher."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict


class AgentResult(BaseModel):
    status: Literal["completed", "needs_review", "blocked"] = "needs_review"
    summary: str = ""
    artifacts: list[str] = []
    tm_comment: str = ""
    brainstorm_consensus: Literal["agreed", "disagreed"] | None = None
    errors: list[str] = []


class AgentContext(BaseModel):
    ticket_id: str
    project_id: str
    agent_id: str
    ticket_title: str
    ticket_type: str | None = None
    description: str
    constraints: str = ""
    relevant_files: str = ""
    project_memory: str = ""
    adrs: str = ""
    agent_config_overrides: str = ""
    brainstorm_project_name: str | None = None
    brainstorm_round: int | None = None
    brainstorm_max_rounds: int | None = None


class AgentRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    ticket_id: str
    project_id: str
    agent_id: str
    runner_mode: str
    status: str
    round_number: int
    brainstorm_session_id: uuid.UUID | None = None
    raw_output: str | None = None
    result: dict | None = None
    error_message: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime


class AgentRunListResponse(BaseModel):
    items: list[AgentRunResponse]
    total: int


class BrainstormSessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    ticket_id: str
    project_name: str
    current_round: int
    max_rounds: int
    status: str
    consensus: str | None = None
    concluded_at: datetime | None = None
    created_at: datetime
