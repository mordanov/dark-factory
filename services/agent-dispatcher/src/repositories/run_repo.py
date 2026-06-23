"""Repository for AgentRun records."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Optional

import structlog
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.models import AgentRun

logger = structlog.get_logger(__name__)


class AgentRunRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(
        self,
        ticket_id: str,
        project_id: str,
        agent_id: str,
        runner_mode: str,
        context_snapshot: dict,
        round_number: int = 1,
        brainstorm_session_id: uuid.UUID | None = None,
    ) -> AgentRun:
        run = AgentRun(
            ticket_id=ticket_id,
            project_id=project_id,
            agent_id=agent_id,
            runner_mode=runner_mode,
            context_snapshot=context_snapshot,
            round_number=round_number,
            brainstorm_session_id=brainstorm_session_id,
            status="pending",
        )
        self.db.add(run)
        await self.db.flush()
        await self.db.refresh(run)
        return run

    async def get_by_id(self, run_id: uuid.UUID) -> AgentRun | None:
        result = await self.db.execute(select(AgentRun).where(AgentRun.id == run_id))
        return result.scalar_one_or_none()

    async def has_running(self, ticket_id: str) -> bool:
        result = await self.db.execute(
            select(AgentRun).where(
                AgentRun.ticket_id == ticket_id,
                AgentRun.status == "running",
            )
        )
        return result.scalar_one_or_none() is not None

    async def mark_running(self, run_id: uuid.UUID) -> None:
        await self.db.execute(
            update(AgentRun)
            .where(AgentRun.id == run_id)
            .values(status="running", started_at=datetime.now(UTC))
        )

    async def mark_done(self, run_id: uuid.UUID, result: dict, raw_output: str) -> None:
        await self.db.execute(
            update(AgentRun)
            .where(AgentRun.id == run_id)
            .values(
                status="completed",
                result=result,
                raw_output=raw_output[:65536] if raw_output else None,
                finished_at=datetime.now(UTC),
            )
        )

    async def mark_failed(
        self, run_id: uuid.UUID, error_message: str, raw_output: str = ""
    ) -> None:
        await self.db.execute(
            update(AgentRun)
            .where(AgentRun.id == run_id)
            .values(
                status="failed",
                error_message=error_message,
                raw_output=raw_output[:65536] if raw_output else None,
                finished_at=datetime.now(UTC),
            )
        )

    async def mark_needs_review(self, run_id: uuid.UUID, result: dict, raw_output: str) -> None:
        await self.db.execute(
            update(AgentRun)
            .where(AgentRun.id == run_id)
            .values(
                status="needs_review",
                result=result,
                raw_output=raw_output[:65536] if raw_output else None,
                finished_at=datetime.now(UTC),
            )
        )

    async def mark_timed_out(
        self, run_id: uuid.UUID, error_message: str, raw_output: str = ""
    ) -> None:
        await self.db.execute(
            update(AgentRun)
            .where(AgentRun.id == run_id)
            .values(
                status="timed_out",
                error_message=error_message,
                raw_output=raw_output[:65536] if raw_output else None,
                finished_at=datetime.now(UTC),
            )
        )

    async def sweep_orphaned_running(self, db: AsyncSession | None = None) -> list[tuple[str, str]]:
        """Mark all running rows as needs_review; return (ticket_id, project_id) pairs."""
        session = db or self.db
        result = await session.execute(select(AgentRun).where(AgentRun.status == "running"))
        orphaned = result.scalars().all()
        affected: list[tuple[str, str]] = []
        for run in orphaned:
            await session.execute(
                update(AgentRun)
                .where(AgentRun.id == run.id)
                .values(
                    status="needs_review",
                    error_message="Service restarted; run orphaned",
                    finished_at=datetime.now(UTC),
                )
            )
            affected.append((run.ticket_id, run.project_id))
        if affected:
            logger.info("Swept orphaned runs", count=len(affected))
        return affected

    async def list_all(
        self,
        ticket_id: str | None = None,
        status: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[AgentRun], int]:
        query = select(AgentRun)
        count_query = select(func.count()).select_from(AgentRun)
        if ticket_id:
            query = query.where(AgentRun.ticket_id == ticket_id)
            count_query = count_query.where(AgentRun.ticket_id == ticket_id)
        if status:
            query = query.where(AgentRun.status == status)
            count_query = count_query.where(AgentRun.status == status)

        total_result = await self.db.execute(count_query)
        total = total_result.scalar_one()

        query = query.offset(offset).limit(limit)
        result = await self.db.execute(query)
        return list(result.scalars().all()), total
