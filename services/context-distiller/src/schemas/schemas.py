"""Pydantic DTOs for ContextDistiller API."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel


class DistillRequest(BaseModel):
    ticket_id: str
    project_id: str


class JobEnqueuedResponse(BaseModel):
    job_id: str


class JobStatusResponse(BaseModel):
    job_id: str
    status: Literal["pending", "running", "done", "failed"]
    error: str | None = None


class MemoryResponse(BaseModel):
    project_id: str
    content: str
    version: int
    last_ticket_id: str
    updated_at: datetime


class AdrCreate(BaseModel):
    content: str
    ticket_id: str
    title: str
    summary: str


class AdrSummary(BaseModel):
    id: str
    title: str
    status: str
    summary: str
    ticket_id: str
    created_at: datetime


class AdrListResponse(BaseModel):
    adrs: list[AdrSummary]


class AdrCreatedResponse(BaseModel):
    adr_id: str


class AdrStatusUpdate(BaseModel):
    status: Literal["proposed", "accepted", "superseded"]


class AdrStatusResponse(BaseModel):
    adr_id: str
    status: str


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str


class AgentOverride(BaseModel):
    agent_id: str
    override_text: str


class AgentConfigRequest(BaseModel):
    project_id: str
    tech_stack: list[str] = []
    agent_overrides: list[AgentOverride] = []


class AgentConfigResponse(BaseModel):
    project_id: str
    tech_stack: list[str]
    agent_overrides: list[AgentOverride]


class AgentConfigStored(BaseModel):
    project_id: str
    stored_at: datetime
