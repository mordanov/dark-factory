"""Pydantic schemas — request/response DTOs."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class OrmModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Ticket Manager domain objects (received from TM API)
# ---------------------------------------------------------------------------


class TmTicket(BaseModel):
    """Full ticket from Ticket Manager including FSM extension fields."""

    id: str
    project_id: str
    title: str
    description: str
    ticket_type: str | None = None  # feature | bugfix | improvement | other
    tags: list[str] = Field(default_factory=list)
    status: str | None = None  # native TM status
    fsm_status: str | None = None  # our FSM state
    blocked_reason: str | None = None
    brainstorm_round: int = 0
    assigned_agent: str | None = None
    override: bool = False
    override_reason: str | None = None
    last_orchestrator_run: datetime | None = None
    orchestrator_errors: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    subtasks: list[str] = Field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None


# ---------------------------------------------------------------------------
# Job Queue
# ---------------------------------------------------------------------------


class JobCreate(BaseModel):
    ticket_id: str
    project_id: str
    job_type: Literal["orchestrate", "distill"] = "orchestrate"
    priority: int = 0
    payload: dict[str, Any] = Field(default_factory=dict)


class JobResponse(OrmModel):
    id: uuid.UUID
    job_type: str
    ticket_id: str
    project_id: str
    status: str
    priority: int
    triggered_by: str
    error_message: str | None
    attempts: int
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class JobListResponse(BaseModel):
    items: list[JobResponse]
    total: int


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------


class AuditLogResponse(OrmModel):
    id: uuid.UUID
    job_id: uuid.UUID | None
    ticket_id: str
    project_id: str
    action: str
    from_state: str | None
    to_state: str | None
    assigned_agent: str | None
    blocked_reason: str | None
    override_logged: bool
    details: str
    created_at: datetime


class AuditListResponse(BaseModel):
    items: list[AuditLogResponse]
    total: int


# ---------------------------------------------------------------------------
# Orchestrator Decision (mirrors system prompt output schema)
# ---------------------------------------------------------------------------


class GateResult(BaseModel):
    gate: str
    passed: bool
    details: dict[str, Any] = Field(default_factory=dict)


class AgentBriefing(BaseModel):
    agent_id: str
    task_summary: str
    relevant_files: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    context_refs: dict[str, list[str]] = Field(default_factory=dict)


class DecisionDetail(BaseModel):
    action: str
    from_state: str | None
    to_state: str | None
    assigned_agent: str | None
    blocked_reason: str | None
    override_logged: bool = False


class OrchestratorDecision(BaseModel):
    """Parsed output from the LLM orchestrator call."""

    orchestrator_version: str = "1.1"
    ticket_id: str
    timestamp: str
    decision: DecisionDetail
    agent_briefing: AgentBriefing | None = None
    gate_results: list[GateResult] = Field(default_factory=list)
    adr: str | None = None
    dependency_check: dict[str, Any] = Field(default_factory=dict)
    context_distiller_trigger: bool = False
    audit_entry: dict[str, str] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# API request schemas
# ---------------------------------------------------------------------------


class TriggerJobRequest(BaseModel):
    """Human triggers processing of a specific ticket."""

    ticket_id: str
    project_id: str
    priority: int = Field(default=0, ge=0, le=10)


class PendingTicketsResponse(BaseModel):
    """Response for the human-facing 'pending tickets' list."""

    tickets: list[TmTicket]
    total: int


# ---------------------------------------------------------------------------
# Document Store
# ---------------------------------------------------------------------------


class ProjectMemoryResponse(BaseModel):
    project_id: str
    content: str
    version: int
    last_ticket_id: str | None
    updated_at: datetime | None


class AdrSummary(BaseModel):
    id: str
    project_id: str
    title: str
    status: str
    summary: str | None
    ticket_id: str | None
    created_at: datetime | None


class AdrListResponse(BaseModel):
    adrs: list[AdrSummary]
