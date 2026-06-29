"""Agent Dispatcher — FastAPI application."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator

from src.api.v1 import consultation, runs, workers, working_memory
from src.core.auth_adapter import prefetch_jwks
from src.core.config import get_settings
from src.core.exceptions import AppError
from src.db.session import AsyncSessionLocal

logger = structlog.get_logger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await prefetch_jwks()

    from src.services.capability_registry import load_registry

    registry = load_registry(settings.resolved_registry_path)
    logger.info("Capability registry loaded", agent_count=len(registry.all_role_ids()))

    from src.repositories.run_repo import AgentRunRepository
    from src.schemas.schemas import AgentResult
    from src.services.reporter import Reporter
    from src.workers.dispatch_worker import DispatchWorker

    async with AsyncSessionLocal() as db:
        repo = AgentRunRepository(db)
        orphaned = await repo.sweep_orphaned_running()
        await db.commit()
        if orphaned:
            logger.info("Swept orphaned runs on startup", count=len(orphaned))
            reporter = Reporter()
            for ticket_id, project_id in orphaned:
                try:
                    await reporter.report_result(
                        ticket_id=ticket_id,
                        project_id=project_id,
                        result=AgentResult(
                            status="needs_review",
                            tm_comment="Service restarted; run orphaned",
                        ),
                    )
                except Exception as exc:
                    logger.warning(
                        "Failed to report orphaned run", ticket_id=ticket_id, error=str(exc)
                    )

    worker = DispatchWorker()
    await worker.start()

    from src.services.worker_service import AgentWorkerService

    async def _liveness_sweep_loop() -> None:
        import asyncio

        while True:
            await asyncio.sleep(60)
            try:
                async with AsyncSessionLocal() as db:
                    svc = AgentWorkerService(db)
                    swept = await svc.run_liveness_sweep()
                    if swept:
                        logger.info("Liveness sweep marked workers unhealthy", count=swept)
                    await db.commit()
            except Exception as exc:
                logger.warning("Liveness sweep error", error=str(exc))

    async def _wm_cleanup_loop() -> None:
        import asyncio

        from src.services.working_memory_service import WorkingMemoryService

        while True:
            await asyncio.sleep(86400)  # daily
            try:
                async with AsyncSessionLocal() as db:
                    svc = WorkingMemoryService(db)
                    deleted = await svc.cleanup_expired()
                    if deleted:
                        logger.info("WM cleanup deleted expired entries", count=deleted)
                    await db.commit()
            except Exception as exc:
                logger.warning("WM cleanup error", error=str(exc))

    sweep_task = asyncio.create_task(_liveness_sweep_loop())
    cleanup_task = asyncio.create_task(_wm_cleanup_loop())

    yield

    sweep_task.cancel()
    cleanup_task.cancel()
    await worker.stop()


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version="1.0.0",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
        )

    app.include_router(runs.router, prefix="/api/v1")
    app.include_router(workers.router, prefix="/api/v1")
    app.include_router(consultation.router, prefix="/api/v1")
    app.include_router(working_memory.router, prefix="/api/v1")

    @app.get("/api/health", tags=["health"])
    async def health():
        return {"status": "ok", "runner_mode": settings.agent_runner_mode}

    Instrumentator().instrument(app).expose(app)

    return app


app = create_app()
