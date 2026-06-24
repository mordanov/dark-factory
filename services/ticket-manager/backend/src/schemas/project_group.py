import re
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, field_validator

_IDENTIFIER_RE = re.compile(r"^[A-Z0-9]{4,8}$")


class ProjectGroupCreate(BaseModel):
    identifier: str
    name: str
    description: str | None = None

    @field_validator("identifier")
    @classmethod
    def normalize_identifier(cls, v: str) -> str:
        normalized = v.strip().upper()
        if not _IDENTIFIER_RE.match(normalized):
            raise ValueError("identifier must be 4–8 alphanumeric characters (letters and digits only)")
        return normalized


class ProjectGroupUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


class ProjectGroupResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: UUID
    identifier: str
    name: str
    description: str | None
    is_system: bool
    created_at: datetime
    project_count: int = 0


class ProjectGroupListResponse(BaseModel):
    items: list[ProjectGroupResponse]
    total: int
