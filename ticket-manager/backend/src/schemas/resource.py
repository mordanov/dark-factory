from uuid import UUID

from pydantic import BaseModel, Field


class TicketResourceIncrementRequest(BaseModel):
    time_spent_delta: int = Field(0, ge=0)
    tokens_consumed_delta: int = Field(0, ge=0)


class TicketResourceIncrementResponse(BaseModel):
    ticket_id: UUID
    time_spent: int
    tokens_consumed: int
    event_id: UUID
