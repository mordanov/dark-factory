from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ProgressUpdateRequest(BaseModel):
    content: str = Field(min_length=1)


class ProgressUpdateResponse(BaseModel):
    ticket_id: UUID
    user_id: UUID
    content: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProgressListResponse(BaseModel):
    items: list[ProgressUpdateResponse]
