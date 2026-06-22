"""User repository.

All SQL for the `users` table lives here.  Services never call SQLAlchemy
directly (SOLID / SRP, DIP).
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.models import User


class UserRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        result = await self._db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        result = await self._db.execute(select(User).where(User.email == email.lower()))
        return result.scalar_one_or_none()

    async def list_all(self, offset: int = 0, limit: int = 100) -> tuple[list[User], int]:
        count_q = select(func.count()).select_from(User)
        total = (await self._db.execute(count_q)).scalar_one()
        users_q = select(User).order_by(User.created_at.desc()).offset(offset).limit(limit)
        users = (await self._db.execute(users_q)).scalars().all()
        return list(users), total

    async def create(
        self, *, email: str, password_hash: str, full_name: str, is_admin: bool
    ) -> User:
        user = User(
            email=email.lower(),
            password_hash=password_hash,
            full_name=full_name,
            is_admin=is_admin,
        )
        self._db.add(user)
        await self._db.flush()
        await self._db.refresh(user)
        return user

    async def update(self, user: User, **fields) -> User:
        for key, value in fields.items():
            setattr(user, key, value)
        await self._db.flush()
        await self._db.refresh(user)
        return user

    async def exists_any(self) -> bool:
        result = await self._db.execute(select(func.count()).select_from(User))
        return (result.scalar_one() or 0) > 0
