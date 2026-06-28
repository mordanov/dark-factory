"""Working memory service — append-only shared memory per ticket."""

from __future__ import annotations

import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.models import WorkingMemoryEntry
from src.repositories.working_memory_repository import WorkingMemoryRepository

logger = structlog.get_logger(__name__)


class WorkingMemoryService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._repo = WorkingMemoryRepository(db)

    async def append(
        self,
        ticket_id: str,
        run_id: uuid.UUID,
        author_role_id: str,
        entry_type: str,
        content: str,
        tags: list[str] | None = None,
    ) -> WorkingMemoryEntry:
        entry = await self._repo.append(
            ticket_id=ticket_id,
            run_id=run_id,
            author_role_id=author_role_id,
            entry_type=entry_type,
            content=content,
            tags=tags,
        )
        logger.debug(
            "Working memory entry appended",
            ticket_id=ticket_id,
            entry_type=entry_type,
            author_role_id=author_role_id,
        )
        return entry

    async def list_for_ticket(
        self,
        ticket_id: str,
        requester_run_id: uuid.UUID | None = None,
        author_role_id: str | None = None,
        entry_type: str | None = None,
        limit: int = 100,
    ) -> list[WorkingMemoryEntry]:
        """List entries for a ticket.

        If requester_run_id is provided, validates the run belongs to that ticket
        and raises PermissionError if it doesn't (cross-ticket isolation).
        """
        if requester_run_id is not None:
            run_ticket = await self._repo.get_run_ticket(requester_run_id)
            if run_ticket is not None and run_ticket != ticket_id:
                raise PermissionError(
                    f"Run {requester_run_id} belongs to ticket {run_ticket!r}, not {ticket_id!r}"
                )

        return await self._repo.list_for_ticket(
            ticket_id=ticket_id,
            author_role_id=author_role_id,
            entry_type=entry_type,
            limit=limit,
        )

    async def cleanup_expired(self) -> int:
        deleted = await self._repo.delete_expired()
        if deleted:
            logger.info("Expired working memory entries cleaned up", count=deleted)
        return deleted
