from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from src.models.ticket import FsmStatus, TicketSpec, TicketStatus, TicketType
from src.models.user import UserRole


class UserSummary(BaseModel):
    id: UUID
    email: str
    role: UserRole

    model_config = {"from_attributes": True}


class AssigneeSummary(BaseModel):
    user_id: UUID
    email: str
    has_progress_update: bool


class TagResponse(BaseModel):
    id: UUID
    name: str

    model_config = {"from_attributes": True}


class TicketCreate(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    description: str | None = None
    ticket_type: TicketType = TicketType.FEATURE
    ticket_spec: TicketSpec
    urgent: bool = False
    blocker: bool = False
    bugfix: bool = False
    tags: list[Annotated[str, Field(min_length=1, max_length=50)]] = Field(default_factory=list)

    @field_validator("tags")
    @classmethod
    def validate_tags_count(cls, v: list[str]) -> list[str]:
        if len(v) > 10:
            raise ValueError("Maximum 10 tags per ticket")
        return v


class FollowUpTicketCreate(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    description: str | None = None
    ticket_type: TicketType = TicketType.FEATURE
    ticket_spec: TicketSpec
    urgent: bool = False
    blocker: bool = False
    bugfix: bool = False
    tags: list[Annotated[str, Field(min_length=1, max_length=50)]] = Field(default_factory=list)

    @field_validator("tags")
    @classmethod
    def validate_tags_count(cls, v: list[str]) -> list[str]:
        if len(v) > 10:
            raise ValueError("Maximum 10 tags per ticket")
        return v


class TicketUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    description: str | None = None
    ticket_type: TicketType | None = None
    ticket_spec: TicketSpec | None = None
    urgent: bool | None = None
    blocker: bool | None = None
    bugfix: bool | None = None


class TicketResponse(BaseModel):
    id: UUID
    display_id: str | None = None
    number: int | None = None
    project_id: UUID
    parent_ticket_id: UUID | None = None
    title: str
    description: str | None = None
    status: TicketStatus
    ticket_type: TicketType = TicketType.FEATURE
    ticket_spec: TicketSpec | None = None
    urgent: bool = False
    blocker: bool = False
    bugfix: bool = False
    time_spent: int = 0
    tokens_consumed: int = 0
    tokens_spent: int = 0
    created_by: UserSummary
    created_at: datetime
    updated_at: datetime
    assignees: list[AssigneeSummary] = []
    follow_up_count: int = 0
    tags: list[TagResponse] = []

    model_config = {"from_attributes": True}


class TicketListResponse(BaseModel):
    tickets: list[TicketResponse]
    total: int


class TokensSpentIncrementRequest(BaseModel):
    amount: int = Field(gt=0, description="Positive integer to add to tokens_spent")


class TokensSpentIncrementResponse(BaseModel):
    ticket_id: UUID
    tokens_spent: int
    amount_added: int
    event_id: UUID


class TagAddRequest(BaseModel):
    name: str = Field(min_length=1, max_length=50)


class FsmPatchRequest(BaseModel):
    fsm_status: FsmStatus | None = None
    blocked_reason: str | None = None
    brainstorm_round: int | None = Field(default=None, ge=0)
    assigned_agent: str | None = None
    override: bool | None = None
    override_reason: str | None = None
    last_orchestrator_run: datetime | None = None
    orchestrator_errors: list[str] | None = None


class TicketFsmResponse(TicketResponse):
    fsm_status: FsmStatus | None = None
    blocked_reason: str | None = None
    brainstorm_round: int = 0
    assigned_agent: str | None = None
    override: bool = False
    override_reason: str | None = None
    last_orchestrator_run: datetime | None = None
    orchestrator_errors: list[str] | None = None


class TicketFsmListResponse(BaseModel):
    tickets: list[TicketFsmResponse]
    total: int


class TagDeltaRequest(BaseModel):
    add: list[Annotated[str, Field(min_length=1, max_length=50)]] = Field(default_factory=list)
    remove: list[Annotated[str, Field(min_length=1, max_length=50)]] = Field(default_factory=list)


class TagDeltaResponse(BaseModel):
    tags: list[str]


class OverrideRequest(BaseModel):
    override: bool
    override_reason: str | None = None


class BatchFsmStatusRequest(BaseModel):
    ticket_ids: list[UUID]


class BatchFsmStatusEntry(BaseModel):
    fsm_status: FsmStatus | None = None
    title: str
    blocked_reason: str | None = None

    model_config = {"from_attributes": True}


class BatchFsmStatusResponse(BaseModel):
    statuses: dict[str, BatchFsmStatusEntry]
