"""Job queue repository — distill jobs only."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Job


def _now() -> datetime:
    return datetime.now(UTC)


class JobRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create_distill_job(
        self,
        ticket_id: str,
        project_id: str,
        payload: dict | None = None,
        triggered_by: str = "api",
    ) -> Job:
        job = Job(
            job_type="distill",
            ticket_id=ticket_id,
            project_id=project_id,
            status="pending",
            payload=payload or {},
            triggered_by=triggered_by,
        )
        self._db.add(job)
        await self._db.flush()
        await self._db.refresh(job)
        return job

    async def get_by_id(self, job_id: uuid.UUID) -> Job | None:
        result = await self._db.execute(select(Job).where(Job.id == job_id))
        return result.scalar_one_or_none()

    async def claim_distill_job(self) -> Job | None:
        """Claim one pending distill job via FOR UPDATE SKIP LOCKED."""
        result = await self._db.execute(
            select(Job)
            .where(Job.job_type == "distill", Job.status == "pending")
            .order_by(Job.priority.desc(), Job.created_at.asc())
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        job = result.scalar_one_or_none()
        if job:
            await self.mark_running(job.id)
        return job

    async def mark_running(self, job_id: uuid.UUID) -> None:
        await self._db.execute(
            update(Job)
            .where(Job.id == job_id)
            .values(
                status="running",
                started_at=_now(),
                attempts=Job.attempts + 1,
            )
        )

    async def mark_done(self, job_id: uuid.UUID) -> None:
        await self._db.execute(
            update(Job).where(Job.id == job_id).values(status="done", finished_at=_now())
        )

    async def mark_failed(self, job_id: uuid.UUID, error_message: str) -> None:
        await self._db.execute(
            update(Job)
            .where(Job.id == job_id)
            .values(status="failed", finished_at=_now(), error_message=error_message)
        )
