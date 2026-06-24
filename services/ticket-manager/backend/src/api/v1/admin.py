from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from src.core.auth_adapter import UserClaims
from src.core.security import require_role
from src.schemas.admin import (
    AdminUserCreate,
    AdminUserListResponse,
    AdminUserResponse,
    AdminUserUpdate,
)

router = APIRouter(prefix="/admin", tags=["Admin"])

_require_admin = require_role("administrator")

_GONE = HTTPException(
    status_code=status.HTTP_410_GONE,
    detail="Local user management has been removed. Use the Keycloak Admin Console.",
)


@router.get("/users", response_model=AdminUserListResponse)
async def list_users(_: UserClaims = _require_admin) -> AdminUserListResponse:
    raise _GONE


@router.post("/users", response_model=AdminUserResponse, status_code=201)
async def create_user(body: AdminUserCreate, _: UserClaims = _require_admin) -> AdminUserResponse:
    raise _GONE


@router.patch("/users/{user_id}", response_model=AdminUserResponse)
async def update_user(
    user_id: UUID, body: AdminUserUpdate, _: UserClaims = _require_admin
) -> AdminUserResponse:
    raise _GONE


@router.post("/users/{user_id}/block", response_model=AdminUserResponse)
async def block_user(user_id: UUID, _: UserClaims = _require_admin) -> AdminUserResponse:
    raise _GONE


@router.post("/users/{user_id}/unblock", response_model=AdminUserResponse)
async def unblock_user(user_id: UUID, _: UserClaims = _require_admin) -> AdminUserResponse:
    raise _GONE
