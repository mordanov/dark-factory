from uuid import UUID

from pydantic import BaseModel

from src.models.ticket import TicketStatus


class TransitionRequest(BaseModel):
    to_status: TicketStatus


class MissingUpdate(BaseModel):
    user_id: UUID
    email: str


class TransitionBlockedError(BaseModel):
    detail: str
    missing_updates: list[MissingUpdate]
