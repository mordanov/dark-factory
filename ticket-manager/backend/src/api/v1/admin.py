from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.security import require_role
from src.models.user import User
from src.schemas.admin import (
    AdminUserCreate,
    AdminUserListResponse,
    AdminUserResponse,
    AdminUserUpdate,
)
from src.services import admin_service

router = APIRouter(prefix="/admin", tags=["Admin"])

_require_admin = require_role("administrator")


@router.get("/users", response_model=AdminUserListResponse)
async def list_users(
    actor: User = _require_admin,
    db: AsyncSession = Depends(get_db),
) -> AdminUserListResponse:
    users = await admin_service.list_users(db)
    items = [AdminUserResponse.model_validate(u) for u in users]
    return AdminUserListResponse(items=items, total=len(items))


@router.post("/users", response_model=AdminUserResponse, status_code=201)
async def create_user(
    body: AdminUserCreate,
    actor: User = _require_admin,
    db: AsyncSession = Depends(get_db),
) -> User:
    return await admin_service.create_user(db, actor, body)


@router.patch("/users/{user_id}", response_model=AdminUserResponse)
async def update_user(
    user_id: UUID,
    body: AdminUserUpdate,
    actor: User = _require_admin,
    db: AsyncSession = Depends(get_db),
) -> User:
    return await admin_service.update_user(db, actor, user_id, body)


@router.post("/users/{user_id}/block", response_model=AdminUserResponse)
async def block_user(
    user_id: UUID,
    actor: User = _require_admin,
    db: AsyncSession = Depends(get_db),
) -> User:
    return await admin_service.block_user(db, actor, user_id)


@router.post("/users/{user_id}/unblock", response_model=AdminUserResponse)
async def unblock_user(
    user_id: UUID,
    actor: User = _require_admin,
    db: AsyncSession = Depends(get_db),
) -> User:
    return await admin_service.unblock_user(db, actor, user_id)
