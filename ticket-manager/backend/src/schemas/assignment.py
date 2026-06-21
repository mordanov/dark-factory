from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class AssignRequest(BaseModel):
    user_id: UUID


class AssignmentResponse(BaseModel):
    ticket_id: UUID
    user_id: UUID
    assigned_at: datetime

    model_config = {"from_attributes": True}
