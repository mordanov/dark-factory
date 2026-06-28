"""Repository for WorkingMemoryEntry — append-only with expiry cleanup."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.models import WorkingMemoryEntry

_RETENTION_DAYS = 30
_MAX_CONTENT_LEN = 65_536


class WorkingMemoryRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def append(
        self,
        ticket_id: str,
        run_id: uuid.UUID,
        author_role_id: str,
        entry_type: str,
        content: str,
        tags: list[str] | None = None,
    ) -> WorkingMemoryEntry:
        if len(content) > _MAX_CONTENT_LEN:
            raise ValueError(f"content exceeds maximum length of {_MAX_CONTENT_LEN} characters")
        entry = WorkingMemoryEntry(
            ticket_id=ticket_id,
            run_id=run_id,
            author_role_id=author_role_id,
            entry_type=entry_type,
            content=content,
            tags=tags or [],
            expires_at=datetime.now(UTC) + timedelta(days=_RETENTION_DAYS),
        )
        self.db.add(entry)
        await self.db.flush()
        await self.db.refresh(entry)
        return entry

    async def list_for_ticket(
        self,
        ticket_id: str,
        author_role_id: str | None = None,
        entry_type: str | None = None,
        since: datetime | None = None,
        limit: int = 100,
    ) -> list[WorkingMemoryEntry]:
        query = (
            select(WorkingMemoryEntry)
            .where(WorkingMemoryEntry.ticket_id == ticket_id)
            .order_by(WorkingMemoryEntry.created_at.asc())
        )
        if author_role_id:
            query = query.where(WorkingMemoryEntry.author_role_id == author_role_id)
        if entry_type:
            query = query.where(WorkingMemoryEntry.entry_type == entry_type)
        if since:
            query = query.where(WorkingMemoryEntry.created_at > since)
        query = query.limit(min(limit, 500))
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_run_ticket(self, run_id: uuid.UUID) -> str | None:
        """Return the ticket_id for the given run_id from agent_runs, or None."""
        from src.models.models import AgentRun

        result = await self.db.execute(select(AgentRun.ticket_id).where(AgentRun.id == run_id))
        return result.scalar_one_or_none()

    async def delete_expired(self) -> int:
        result = await self.db.execute(
            delete(WorkingMemoryEntry).where(WorkingMemoryEntry.expires_at < datetime.now(UTC))
        )
        return result.rowcount  # type: ignore[return-value]
