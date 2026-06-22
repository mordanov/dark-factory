"""Jobs API — human-facing endpoints.

Human opens the UI, sees a list of tickets awaiting orchestration,
selects one (or several), and triggers processing.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_current_user, get_doc_store, get_tm
from src.core.config import get_settings
from src.db.postgres import get_db
from src.repositories.job_repo import JobRepository
from src.schemas.schemas import (
    JobListResponse,
    JobResponse,
    PendingTicketsResponse,
    TriggerJobRequest,
)
from src.services.document_store.store import DocumentStore
from src.services.tm_client.client import TicketManagerClient
from src.workers.job_worker import get_worker, notify_new_job

router = APIRouter(prefix="/jobs", tags=["jobs"])
settings = get_settings()


@router.get("/pending-tickets", response_model=PendingTicketsResponse)
async def list_pending_tickets(
    project_id: str | None = Query(default=None),
    _: dict = Depends(get_current_user),
    tm: TicketManagerClient = Depends(get_tm),
):
    """Return all tickets from TM that are awaiting orchestrator processing.

    This is the main list the human sees before triggering a job.
    """
    tickets_raw = await tm.get_pending_tickets(project_id=project_id)
    from src.schemas.schemas import TmTicket

    tickets = [TmTicket(**t) for t in tickets_raw]
    return PendingTicketsResponse(tickets=tickets, total=len(tickets))


@router.post("/trigger", response_model=JobResponse, status_code=201)
async def trigger_job(
    payload: TriggerJobRequest,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Human triggers orchestration for a specific ticket."""
    repo = JobRepository(db)

    # Guard: don't enqueue if already running
    if await repo.has_running_job(payload.ticket_id):
        from fastapi import HTTPException

        raise HTTPException(409, "A job for this ticket is already running")

    job = await repo.create(
        job_type="orchestrate",
        ticket_id=payload.ticket_id,
        project_id=payload.project_id,
        priority=payload.priority,
        triggered_by=user.get("sub", "unknown"),
        payload={},
    )
    await notify_new_job(settings.database_url)
    return JobResponse.model_validate(job)


@router.get("", response_model=JobListResponse)
async def list_jobs(
    status: str | None = Query(default=None),
    ticket_id: str | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    _: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    repo = JobRepository(db)
    jobs, total = await repo.list_all(
        status=status, ticket_id=ticket_id, offset=offset, limit=limit
    )
    items = [JobResponse.model_validate(j) for j in jobs]
    return JobListResponse(items=items, total=total)


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: uuid.UUID,
    _: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    repo = JobRepository(db)
    job = await repo.get_by_id(job_id)
    if not job:
        from src.core.exceptions import NotFoundError

        raise NotFoundError("Job not found")
    return JobResponse.model_validate(job)
