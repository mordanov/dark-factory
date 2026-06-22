import re
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, field_validator

_CODE_RE = re.compile(r"^[A-Z]{4}-\d{3}$")


class ProjectCreate(BaseModel):
    name: str
    code: str

    @field_validator("code")
    @classmethod
    def validate_code(cls, v: str) -> str:
        if not _CODE_RE.match(v):
            raise ValueError("code must match AAAA-NNN (4 uppercase letters, hyphen, 3 digits)")
        return v


class ProjectTicketCounts(BaseModel):
    open: int
    active: int
    done: int


class ProjectResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: UUID
    name: str
    slug: str
    code: str | None
    created_at: datetime
    ticket_counts: ProjectTicketCounts
