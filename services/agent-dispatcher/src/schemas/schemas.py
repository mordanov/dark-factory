"""Pydantic schemas for Agent Dispatcher."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class AgentResult(BaseModel):
    status: Literal["completed", "needs_review", "blocked"] = "needs_review"
    summary: str = ""
    artifacts: list[str] = []
    tm_comment: str = ""
    brainstorm_consensus: Literal["agreed", "disagreed"] | None = None
    errors: list[str] = []
    matched_capability_record: dict | None = None


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


# ---------------------------------------------------------------------------
# Worker lifecycle schemas (US2)
# ---------------------------------------------------------------------------


class WorkerRegisterRequest(BaseModel):
    role_id: str
    version: str
    capabilities_snapshot: dict = Field(default_factory=dict)


class WorkerRegisterResponse(BaseModel):
    worker_id: uuid.UUID
    role_id: str
    status: str
    registered_at: datetime


class HeartbeatRequest(BaseModel):
    worker_id: uuid.UUID
    status: str | None = None  # idle | busy | draining


class HeartbeatResponse(BaseModel):
    acknowledged: bool
    next_heartbeat_deadline: datetime


class DrainRequest(BaseModel):
    worker_id: uuid.UUID


class DrainResponse(BaseModel):
    worker_id: uuid.UUID
    status: str
    offline_at: datetime | None = None


class WorkerRecord(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role_id: str
    status: str
    version: str
    last_heartbeat_at: datetime
    registered_at: datetime


class WorkerListResponse(BaseModel):
    workers: list[WorkerRecord]
    total: int


# ---------------------------------------------------------------------------
# Consultation schemas (US3)
# ---------------------------------------------------------------------------


class ConsultRequest(BaseModel):
    requesting_role_id: str
    run_id: uuid.UUID
    ticket_id: str
    required_peer_capabilities: list[str]
    question: str = Field(max_length=2048)
    context_summary: str = Field(default="", max_length=1024)
    timeout_seconds: int = Field(default=60, ge=1, le=120)


class ConsultResponse(BaseModel):
    consultation_id: uuid.UUID
    peer_role_id: str
    answer: str
    peer_capability_record: dict
    latency_ms: int


# ---------------------------------------------------------------------------
# Working memory schemas (US4)
# ---------------------------------------------------------------------------


class WorkingMemoryEntryCreate(BaseModel):
    run_id: uuid.UUID
    author_role_id: str
    entry_type: Literal["observation", "decision", "artifact_ref", "question", "answer"]
    content: str = Field(max_length=65536)
    tags: list[str] = Field(default_factory=list)


class WorkingMemoryEntryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    author_role_id: str
    entry_type: str
    content: str
    tags: list[str]
    created_at: datetime
    run_id: uuid.UUID


class WorkingMemoryListResponse(BaseModel):
    ticket_id: str
    entries: list[WorkingMemoryEntryResponse]
    total: int
    has_more: bool


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
