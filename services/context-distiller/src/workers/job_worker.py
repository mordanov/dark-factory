"""Async job worker — PostgreSQL LISTEN/NOTIFY + poll fallback."""

from __future__ import annotations

import asyncio
import logging
import uuid

import asyncpg

from src.core.config import get_settings
from src.db.mongo import get_mongo_db
from src.db.postgres import AsyncSessionFactory
from src.repositories.job_repo import JobRepository
from src.repositories.memory_repo import MemoryRepository
from src.services.data_collector import DataCollector
from src.services.distiller import distill
from src.services.tm_client import TMClient

logger = logging.getLogger(__name__)
settings = get_settings()

NOTIFY_CHANNEL = "df_new_job"


class JobWorker:
    def __init__(self) -> None:
        self._sem = asyncio.Semaphore(settings.worker_max_concurrent_jobs)
        self._running = False
        self._tasks: set[asyncio.Task] = set()

    async def start(self) -> None:
        self._running = True
        logger.info("JobWorker starting (max_concurrent=%d)", settings.worker_max_concurrent_jobs)
        asyncio.create_task(self._listen_loop())

    async def stop(self) -> None:
        self._running = False
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

    async def _listen_loop(self) -> None:
        pg_dsn = settings.database_url.replace("+asyncpg", "")
        while self._running:
            try:
                conn = await asyncpg.connect(pg_dsn)
                await conn.add_listener(NOTIFY_CHANNEL, self._on_notify)
                logger.info("Listening on PG channel '%s'", NOTIFY_CHANNEL)
                await self._sweep()
                while self._running:
                    await asyncio.sleep(settings.worker_poll_interval_seconds)
                    await self._sweep()
                await conn.remove_listener(NOTIFY_CHANNEL, self._on_notify)
                await conn.close()
            except Exception as exc:
                logger.error("Worker listen loop error: %s — reconnecting in 5s", exc)
                await asyncio.sleep(5)

    def _on_notify(self, conn, pid, channel, payload) -> None:
        asyncio.create_task(self._sweep())

    async def _sweep(self) -> None:
        for _ in range(settings.worker_max_concurrent_jobs):
            async with AsyncSessionFactory() as db:
                repo = JobRepository(db)
                job = await repo.claim_distill_job()
                await db.commit()
                if not job:
                    break
            task = asyncio.create_task(self._run_job(job.id))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)

    async def _run_job(self, job_id: uuid.UUID) -> None:
        async with self._sem:
            async with AsyncSessionFactory() as db:
                job_repo = JobRepository(db)
                job = await job_repo.get_by_id(job_id)
                if not job:
                    logger.warning("Job %s not found — skipping", job_id)
                    return
                mongo_db = get_mongo_db()
                tm = TMClient()
                try:
                    collector = DataCollector(tm, db, mongo_db)
                    ctx = await collector.collect(job.ticket_id, job.project_id)
                    yaml_content = await distill(ctx)
                    memory_repo = MemoryRepository(mongo_db)
                    await memory_repo.archive_then_write(
                        job.project_id, yaml_content, job.ticket_id
                    )
                    await job_repo.mark_done(job_id)
                    await db.commit()
                    logger.info("Job %s completed successfully", job_id)
                except Exception as exc:
                    logger.error("Job %s failed: %s", job_id, exc)
                    raw = getattr(exc, "raw_output", str(exc))
                    await job_repo.mark_failed(job_id, raw[:4000])
                    await db.commit()
                finally:
                    await tm.aclose()
