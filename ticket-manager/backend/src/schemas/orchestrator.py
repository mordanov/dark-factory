import base64
import json
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from src.models.ticket import FsmStatus


def encode_cursor(updated_at: datetime, ticket_id: UUID) -> str:
    data = {"updated_at": updated_at.isoformat(), "id": str(ticket_id)}
    return base64.urlsafe_b64encode(json.dumps(data).encode()).decode()


def decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    data = json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())
    return datetime.fromisoformat(data["updated_at"]), UUID(data["id"])


class AuditEventCreate(BaseModel):
    event: str = Field(min_length=1, max_length=50)
    actor: str = Field(min_length=1, max_length=255)
    from_state: str | None = Field(default=None, max_length=50)
    to_state: str | None = Field(default=None, max_length=50)
    details: str | None = None
    timestamp: datetime | None = None


class AuditEventResponse(BaseModel):
    id: UUID
    ticket_id: UUID
    event: str
    actor: str
    from_state: str | None = None
    to_state: str | None = None
    details: str | None = None
    timestamp: datetime

    model_config = {"from_attributes": True}


class AuditLogResponse(BaseModel):
    ticket_id: UUID
    entries: list[AuditEventResponse]


class TicketPendingSummary(BaseModel):
    id: UUID
    project_id: UUID
    title: str
    status: str
    fsm_status: FsmStatus | None = None
    blocked_reason: str | None = None
    brainstorm_round: int = 0
    assigned_agent: str | None = None
    override: bool = False
    last_orchestrator_run: datetime | None = None
    created_at: datetime
    updated_at: datetime
    follow_up_ids: list[UUID] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class PendingTicketsResponse(BaseModel):
    tickets: list[TicketPendingSummary]
    total_pending: int
    next_cursor: str | None = None
