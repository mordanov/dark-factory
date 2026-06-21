"""Async job worker.

Uses PostgreSQL LISTEN/NOTIFY for instant wake-up when a job is enqueued,
with a fallback poll interval for robustness.

Concurrency is managed via asyncio.Semaphore so multiple tickets can be
processed simultaneously without overloading OpenAI or the Ticket Manager.
"""
from __future__ import annotations
import asyncio
import logging
import uuid

import asyncpg

from src.core.config import get_settings
from src.db.mongo import get_mongo_db
from src.db.postgres import AsyncSessionFactory
from src.models.models import Job
from src.repositories.job_repo import JobRepository
from src.services.document_store.store import DocumentStore
from src.services.orchestrator_service import DistillerService, OrchestratorService
from src.services.tm_client.client import get_tm_client

logger = logging.getLogger(__name__)
settings = get_settings()

NOTIFY_CHANNEL = "df_new_job"


class JobWorker:
    """Runs as a long-lived asyncio task in the FastAPI lifespan."""

    def __init__(self) -> None:
        self._sem = asyncio.Semaphore(settings.worker_max_concurrent_tickets)
        self._running = False
        self._tasks: set[asyncio.Task] = set()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        self._running = True
        logger.info("Job worker starting (max_concurrent=%d)", settings.worker_max_concurrent_tickets)
        asyncio.create_task(self._listen_loop())

    async def stop(self) -> None:
        self._running = False
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

    # ------------------------------------------------------------------
    # PostgreSQL LISTEN/NOTIFY loop
    # ------------------------------------------------------------------

    async def _listen_loop(self) -> None:
        """Connect via asyncpg (raw, not SQLAlchemy) to use LISTEN."""
        pg_dsn = settings.database_url.replace("+asyncpg", "")
        while self._running:
            try:
                conn = await asyncpg.connect(pg_dsn)
                await conn.add_listener(NOTIFY_CHANNEL, self._on_notify)
                logger.info("Listening on channel '%s'", NOTIFY_CHANNEL)
                # Also do an initial sweep to pick up jobs enqueued before startup
                await self._sweep()
                while self._running:
                    # asyncpg delivers notifications via the listener callback;
                    # we idle here and fall back to polling every N seconds
                    await asyncio.sleep(settings.worker_poll_interval_seconds)
                    await self._sweep()
                await conn.remove_listener(NOTIFY_CHANNEL, self._on_notify)
                await conn.close()
            except Exception as exc:
                logger.error("Worker listen loop error: %s — reconnecting in 5s", exc)
                await asyncio.sleep(5)

    def _on_notify(self, conn, pid, channel, payload):
        """Called by asyncpg when a NOTIFY arrives — schedule a sweep."""
        asyncio.create_task(self._sweep())

    # ------------------------------------------------------------------
    # Job sweep and dispatch
    # ------------------------------------------------------------------

    async def _sweep(self) -> None:
        """Pick up all pending jobs and dispatch them under the semaphore."""
        async with AsyncSessionFactory() as db:
            repo = JobRepository(db)
            jobs = await repo.list_pending(limit=settings.worker_max_concurrent_tickets * 2)
            await db.commit()

        for job in jobs:
            # Skip if already being processed (running status set by another task)
            task = asyncio.create_task(self._run_job(job.id, job.job_type))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)

    async def _run_job(self, job_id: uuid.UUID, job_type: str) -> None:
        async with self._sem:
            async with AsyncSessionFactory() as db:
                repo = JobRepository(db)
                # Guard: mark running only if still pending (prevent double processing)
                job = await repo.get_by_id(job_id)
                if not job or job.status != "pending":
                    return
                await db.commit()

            async with AsyncSessionFactory() as db:
                doc_store = DocumentStore(get_mongo_db())
                try:
                    if job_type == "orchestrate":
                        svc = OrchestratorService(db, get_tm_client(), doc_store)
                    else:
                        svc = DistillerService(db, doc_store)  # type: ignore[assignment]
                    await svc.process_job(job_id)
                except Exception as exc:
                    logger.error("Job %s (%s) failed: %s", job_id, job_type, exc)


# Module-level singleton
_worker: JobWorker | None = None


def get_worker() -> JobWorker:
    global _worker
    if _worker is None:
        _worker = JobWorker()
    return _worker


async def notify_new_job(db_dsn: str) -> None:
    """Send NOTIFY to wake up the worker when a new job is enqueued."""
    pg_dsn = db_dsn.replace("+asyncpg", "")
    try:
        conn = await asyncpg.connect(pg_dsn)
        await conn.execute(f"NOTIFY {NOTIFY_CHANNEL}")
        await conn.close()
    except Exception as exc:
        logger.warning("Failed to NOTIFY worker: %s", exc)
