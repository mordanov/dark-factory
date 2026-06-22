"""FastAPI application entry point."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from src.api.v1.distill import router as distill_router
from src.api.v1.memory import router as memory_router
from src.core.exceptions import ConflictError, NotFoundError, UpstreamError
from src.schemas.schemas import HealthResponse
from src.workers.job_worker import JobWorker

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_worker: JobWorker | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _worker
    _worker = JobWorker()
    await _worker.start()
    yield
    if _worker:
        await _worker.stop()


app = FastAPI(title="ContextDistiller", version="1.0.0", lifespan=lifespan)

app.include_router(distill_router)
app.include_router(memory_router)


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok", service="context-distiller")


@app.exception_handler(NotFoundError)
async def not_found_handler(request: Request, exc: NotFoundError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(ConflictError)
async def conflict_handler(request: Request, exc: ConflictError) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.exception_handler(UpstreamError)
async def upstream_handler(request: Request, exc: UpstreamError) -> JSONResponse:
    return JSONResponse(status_code=502, content={"detail": str(exc)})
