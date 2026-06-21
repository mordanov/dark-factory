"""Dark Factory Orchestrator — FastAPI application."""
from __future__ import annotations
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.v1 import audit, jobs, memory
from src.core.config import get_settings
from src.core.exceptions import AppError, app_error_handler
from src.db.mongo import close_mongo
from src.workers.job_worker import get_worker

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    worker = get_worker()
    await worker.start()
    yield
    await worker.stop()
    await close_mongo()


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

    app.add_exception_handler(AppError, app_error_handler)

    for router in [jobs.router, audit.router, memory.router]:
        app.include_router(router, prefix="/api/v1")

    @app.get("/api/health", tags=["health"])
    async def health():
        return {"status": "ok", "service": settings.app_name}

    return app


app = create_app()
