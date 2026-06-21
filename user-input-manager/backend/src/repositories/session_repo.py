"""Session and Iteration repositories."""
from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.models import PromptIteration, PromptSession


class SessionRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_by_id(self, session_id: uuid.UUID) -> PromptSession | None:
        result = await self._db.execute(
            select(PromptSession)
            .where(PromptSession.id == session_id)
            .options(selectinload(PromptSession.iterations))
        )
        return result.scalar_one_or_none()

    async def get_by_id_and_user(
        self, session_id: uuid.UUID, user_id: uuid.UUID
    ) -> PromptSession | None:
        result = await self._db.execute(
            select(PromptSession)
            .where(
                PromptSession.id == session_id,
                PromptSession.user_id == user_id,
            )
            .options(selectinload(PromptSession.iterations))
        )
        return result.scalar_one_or_none()

    async def list_for_user(
        self, user_id: uuid.UUID, offset: int = 0, limit: int = 50
    ) -> tuple[list[PromptSession], int]:
        count_q = (
            select(func.count())
            .select_from(PromptSession)
            .where(PromptSession.user_id == user_id)
        )
        total = (await self._db.execute(count_q)).scalar_one()
        q = (
            select(PromptSession)
            .where(PromptSession.user_id == user_id)
            .order_by(PromptSession.updated_at.desc())
            .offset(offset)
            .limit(limit)
        )
        sessions = (await self._db.execute(q)).scalars().all()
        return list(sessions), total

    async def create(self, **kwargs) -> PromptSession:
        session = PromptSession(**kwargs)
        self._db.add(session)
        await self._db.flush()
        await self._db.refresh(session)
        return session

    async def update(self, session: PromptSession, **fields) -> PromptSession:
        for k, v in fields.items():
            setattr(session, k, v)
        await self._db.flush()
        await self._db.refresh(session)
        return session


class IterationRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_by_id(self, iteration_id: uuid.UUID) -> PromptIteration | None:
        result = await self._db.execute(
            select(PromptIteration).where(PromptIteration.id == iteration_id)
        )
        return result.scalar_one_or_none()

    async def list_for_session(self, session_id: uuid.UUID) -> list[PromptIteration]:
        result = await self._db.execute(
            select(PromptIteration)
            .where(PromptIteration.session_id == session_id)
            .order_by(PromptIteration.iteration_number)
        )
        return list(result.scalars().all())

    async def create(self, **kwargs) -> PromptIteration:
        iteration = PromptIteration(**kwargs)
        self._db.add(iteration)
        await self._db.flush()
        await self._db.refresh(iteration)
        return iteration

    async def update(self, iteration: PromptIteration, **fields) -> PromptIteration:
        for k, v in fields.items():
            setattr(iteration, k, v)
        await self._db.flush()
        await self._db.refresh(iteration)
        return iteration

    async def delete_from_number(self, session_id: uuid.UUID, from_number: int) -> None:
        """Delete all iterations with number >= from_number (used for revert)."""
        iterations = await self._db.execute(
            select(PromptIteration).where(
                PromptIteration.session_id == session_id,
                PromptIteration.iteration_number >= from_number,
            )
        )
        for it in iterations.scalars().all():
            await self._db.delete(it)
        await self._db.flush()

    async def max_number(self, session_id: uuid.UUID) -> int:
        result = await self._db.execute(
            select(func.max(PromptIteration.iteration_number)).where(
                PromptIteration.session_id == session_id
            )
        )
        return result.scalar_one() or 0
