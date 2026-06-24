from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class AssignRequest(BaseModel):
    user_id: str


class AssignmentResponse(BaseModel):
    ticket_id: UUID
    user_id: str
    assigned_at: datetime

    model_config = {"from_attributes": True}
