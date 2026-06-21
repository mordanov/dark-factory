"""POST /distill and GET /status/{job_id} endpoints."""
from __future__ import annotations
import asyncio
import uuid
from typing import Annotated

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, status

from src.api.dependencies import DbDep, MongoDep, UserDep
from src.core.config import get_settings
from src.repositories.job_repo import JobRepository
from src.schemas.schemas import DistillRequest, JobEnqueuedResponse, JobStatusResponse

router = APIRouter()
NOTIFY_CHANNEL = "df_new_job"


@router.post("/distill", response_model=JobEnqueuedResponse, status_code=202)
async def enqueue_distill(
    body: DistillRequest,
    db: DbDep,
    _user: UserDep,
) -> JobEnqueuedResponse:
    repo = JobRepository(db)
    job = await repo.create_distill_job(
        ticket_id=body.ticket_id,
        project_id=body.project_id,
        triggered_by="api",
    )
    await db.commit()

    # Fire-and-forget NOTIFY so the worker wakes immediately
    settings = get_settings()
    try:
        pg_dsn = settings.database_url.replace("+asyncpg", "")
        conn = await asyncpg.connect(pg_dsn)
        await conn.execute(f"NOTIFY {NOTIFY_CHANNEL}")
        await conn.close()
    except Exception:
        pass  # Worker will pick it up on next poll

    return JobEnqueuedResponse(job_id=str(job.id))


@router.get("/status/{job_id}", response_model=JobStatusResponse)
async def get_job_status(
    job_id: uuid.UUID,
    db: DbDep,
    _user: UserDep,
) -> JobStatusResponse:
    repo = JobRepository(db)
    job = await repo.get_by_id(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobStatusResponse(
        job_id=str(job.id),
        status=job.status,
        error=job.error_message,
    )
