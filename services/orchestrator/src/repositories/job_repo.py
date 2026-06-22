"""Job queue repository."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timezone

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.models import Job


class JobRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create(self, **kwargs) -> Job:
        job = Job(**kwargs)
        self._db.add(job)
        await self._db.flush()
        await self._db.refresh(job)
        return job

    async def get_by_id(self, job_id: uuid.UUID) -> Job | None:
        result = await self._db.execute(select(Job).where(Job.id == job_id))
        return result.scalar_one_or_none()

    async def list_pending(self, limit: int = 50) -> list[Job]:
        """Return pending jobs ordered by priority (desc) then created_at (asc)."""
        result = await self._db.execute(
            select(Job)
            .where(Job.status == "pending")
            .order_by(Job.priority.desc(), Job.created_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def list_all(
        self,
        status: str | None = None,
        ticket_id: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[Job], int]:
        q = select(Job)
        if status:
            q = q.where(Job.status == status)
        if ticket_id:
            q = q.where(Job.ticket_id == ticket_id)
        count = (
            await self._db.execute(select(func.count()).select_from(q.subquery()))
        ).scalar_one()
        q = q.order_by(Job.created_at.desc()).offset(offset).limit(limit)
        jobs = list((await self._db.execute(q)).scalars().all())
        return jobs, count

    async def mark_running(self, job_id: uuid.UUID) -> None:
        await self._db.execute(
            update(Job)
            .where(Job.id == job_id)
            .values(status="running", started_at=datetime.now(UTC), attempts=Job.attempts + 1)
        )
        await self._db.flush()

    async def mark_done(self, job_id: uuid.UUID, result: dict) -> None:
        await self._db.execute(
            update(Job)
            .where(Job.id == job_id)
            .values(status="done", result=result, finished_at=datetime.now(UTC))
        )
        await self._db.flush()

    async def mark_failed(self, job_id: uuid.UUID, error: str) -> None:
        await self._db.execute(
            update(Job)
            .where(Job.id == job_id)
            .values(status="failed", error_message=error, finished_at=datetime.now(UTC))
        )
        await self._db.flush()

    async def has_running_job(self, ticket_id: str) -> bool:
        result = await self._db.execute(
            select(func.count())
            .select_from(Job)
            .where(Job.ticket_id == ticket_id, Job.status == "running")
        )
        return (result.scalar_one() or 0) > 0
