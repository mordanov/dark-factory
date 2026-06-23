"""Repository for BrainstormSession records."""

from __future__ import annotations

from datetime import UTC, datetime

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.models import BrainstormSession

logger = structlog.get_logger(__name__)


class BrainstormSessionRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_or_create(self, ticket_id: str, max_rounds: int = 3) -> BrainstormSession:
        result = await self.db.execute(
            select(BrainstormSession).where(BrainstormSession.ticket_id == ticket_id)
        )
        existing = result.scalar_one_or_none()
        if existing is not None:
            return existing

        session = BrainstormSession(
            ticket_id=ticket_id,
            project_name=f"df-{ticket_id}",
            max_rounds=max_rounds,
        )
        self.db.add(session)
        await self.db.flush()
        await self.db.refresh(session)
        return session

    async def increment_round(self, session_id) -> None:
        await self.db.execute(
            update(BrainstormSession)
            .where(BrainstormSession.id == session_id)
            .values(current_round=BrainstormSession.current_round + 1)
        )

    async def conclude(self, session_id, consensus: str | None) -> None:
        await self.db.execute(
            update(BrainstormSession)
            .where(BrainstormSession.id == session_id)
            .values(
                status="concluded",
                consensus=consensus,
                concluded_at=datetime.now(UTC),
            )
        )
