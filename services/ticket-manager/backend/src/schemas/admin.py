from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from src.models.user import UserRole


class AdminUserResponse(BaseModel):
    id: UUID
    email: str
    role: UserRole
    created_at: datetime
    blocked_at: datetime | None

    model_config = {"from_attributes": True}


class AdminUserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    role: UserRole = UserRole.user


class AdminUserUpdate(BaseModel):
    email: EmailStr | None = None
    role: UserRole | None = None
    password: str | None = Field(None, min_length=8)


class AdminUserListResponse(BaseModel):
    items: list[AdminUserResponse]
    total: int
