"""User management service (admin operations)."""
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ConflictError, NotFoundError
from src.core.security import hash_password
from src.repositories.user_repo import UserRepository
from src.schemas.schemas import UserCreate, UserListResponse, UserResponse, UserUpdate


class UserService:
    def __init__(self, db: AsyncSession) -> None:
        self._repo = UserRepository(db)

    async def create_user(self, payload: UserCreate) -> UserResponse:
        existing = await self._repo.get_by_email(payload.email)
        if existing:
            raise ConflictError("Email already registered")
        user = await self._repo.create(
            email=payload.email,
            password_hash=hash_password(payload.password),
            full_name=payload.full_name,
            is_admin=payload.is_admin,
        )
        return UserResponse.model_validate(user)

    async def list_users(self, offset: int = 0, limit: int = 100) -> UserListResponse:
        users, total = await self._repo.list_all(offset=offset, limit=limit)
        return UserListResponse(items=[UserResponse.model_validate(u) for u in users], total=total)

    async def get_user(self, user_id: uuid.UUID) -> UserResponse:
        user = await self._repo.get_by_id(user_id)
        if not user:
            raise NotFoundError("User not found")
        return UserResponse.model_validate(user)

    async def update_user(self, user_id: uuid.UUID, payload: UserUpdate) -> UserResponse:
        user = await self._repo.get_by_id(user_id)
        if not user:
            raise NotFoundError("User not found")

        updates: dict = {}
        if payload.email is not None:
            conflict = await self._repo.get_by_email(payload.email)
            if conflict and conflict.id != user.id:
                raise ConflictError("Email already in use")
            updates["email"] = payload.email.lower()
        if payload.full_name is not None:
            updates["full_name"] = payload.full_name
        if payload.is_admin is not None:
            updates["is_admin"] = payload.is_admin
        if payload.is_active is not None:
            updates["is_active"] = payload.is_active
        if payload.password is not None:
            updates["password_hash"] = hash_password(payload.password)

        user = await self._repo.update(user, **updates)
        return UserResponse.model_validate(user)
