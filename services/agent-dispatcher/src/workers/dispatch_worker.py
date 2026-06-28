"""DispatchWorker — async polling loop with concurrency semaphore."""

from __future__ import annotations

import asyncio

import structlog

from src.core.config import get_settings
from src.db.session import AsyncSessionLocal

logger = structlog.get_logger(__name__)


class DispatchWorker:
    def __init__(self) -> None:
        settings = get_settings()
        self._semaphore = asyncio.Semaphore(settings.worker_max_concurrent_runs)
        self._loop_task: asyncio.Task | None = None
        self._running = False

    async def start(self) -> None:
        self._running = True
        self._loop_task = asyncio.create_task(self._poll_loop())
        logger.info("DispatchWorker started")

    async def stop(self) -> None:
        self._running = False
        if self._loop_task:
            self._loop_task.cancel()
            try:
                await self._loop_task
            except asyncio.CancelledError:
                pass
        logger.info("DispatchWorker stopped")

    async def _poll_loop(self) -> None:
        settings = get_settings()
        from src.services.dispatcher_service import process_ticket
        from src.services.poller import poll_once

        while self._running:
            try:
                async with AsyncSessionLocal() as db:
                    tickets = await poll_once(db)

                for ticket in tickets:
                    asyncio.create_task(self._run_with_semaphore(ticket))

            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error("Poll loop error", error=str(exc))

            await asyncio.sleep(settings.poll_interval_seconds)

    async def _run_with_semaphore(self, ticket) -> None:
        from src.services.dispatcher_service import process_ticket

        async with self._semaphore:
            try:
                async with AsyncSessionLocal() as db:
                    await process_ticket(
                        ticket,
                        db,
                        required_capabilities=getattr(ticket, "required_capabilities", None),
                    )
                    await db.commit()
            except Exception as exc:
                logger.error(
                    "Unhandled error in process_ticket",
                    ticket_id=ticket.id,
                    error=str(exc),
                )
