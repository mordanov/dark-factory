from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class TicketEventResponse(BaseModel):
    id: UUID
    ticket_id: UUID
    event_type: str
    actor_id: str
    prev_state: dict[str, Any] | None = None
    new_state: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None
    occurred_at: datetime

    model_config = {"from_attributes": True}


class EventListResponse(BaseModel):
    items: list[TicketEventResponse]
