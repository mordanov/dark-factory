import re
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, field_validator

from src.schemas.project_group import ProjectGroupResponse

_CODE_RE = re.compile(r"^[A-Z]{4}-\d{3}$")


class ProjectCreate(BaseModel):
    name: str
    code: str | None = None
    group_id: UUID | None = None

    @field_validator("code")
    @classmethod
    def validate_code(cls, v: str | None) -> str | None:
        if v is not None and not _CODE_RE.match(v):
            raise ValueError("code must match AAAA-NNN (4 uppercase letters, hyphen, 3 digits)")
        return v


class ProjectUpdate(BaseModel):
    group_id: UUID | None = None


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
    group_id: UUID
    group: ProjectGroupResponse
    created_at: datetime
    ticket_counts: ProjectTicketCounts
