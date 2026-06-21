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
    ticket_type: Optional[str] = None       # feature | bugfix | improvement | other
    tags: list[str] = Field(default_factory=list)
    status: Optional[str] = None            # native TM status
    fsm_status: Optional[str] = None        # our FSM state
    blocked_reason: Optional[str] = None
    brainstorm_round: int = 0
    assigned_agent: Optional[str] = None
    override: bool = False
    override_reason: Optional[str] = None
    last_orchestrator_run: Optional[datetime] = None
    orchestrator_errors: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    subtasks: list[str] = Field(default_factory=list)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


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
    error_message: Optional[str]
    attempts: int
    created_at: datetime
    started_at: Optional[datetime]
    finished_at: Optional[datetime]


class JobListResponse(BaseModel):
    items: list[JobResponse]
    total: int


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------

class AuditLogResponse(OrmModel):
    id: uuid.UUID
    job_id: Optional[uuid.UUID]
    ticket_id: str
    project_id: str
    action: str
    from_state: Optional[str]
    to_state: Optional[str]
    assigned_agent: Optional[str]
    blocked_reason: Optional[str]
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
    from_state: Optional[str]
    to_state: Optional[str]
    assigned_agent: Optional[str]
    blocked_reason: Optional[str]
    override_logged: bool = False


class OrchestratorDecision(BaseModel):
    """Parsed output from the LLM orchestrator call."""
    orchestrator_version: str = "1.1"
    ticket_id: str
    timestamp: str
    decision: DecisionDetail
    agent_briefing: Optional[AgentBriefing] = None
    gate_results: list[GateResult] = Field(default_factory=list)
    adr: Optional[str] = None
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
    last_ticket_id: Optional[str]
    updated_at: Optional[datetime]


class AdrSummary(BaseModel):
    id: str
    project_id: str
    title: str
    status: str
    summary: Optional[str]
    ticket_id: Optional[str]
    created_at: Optional[datetime]


class AdrListResponse(BaseModel):
    adrs: list[AdrSummary]
