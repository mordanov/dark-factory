"""Minimal FastAPI sidecar for agent-tools health endpoint and auth adapter."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.core.auth_adapter import prefetch_jwks


@asynccontextmanager
async def lifespan(app: FastAPI):
    await prefetch_jwks()
    yield


app = FastAPI(title="agent-tools-sidecar", docs_url=None, redoc_url=None, lifespan=lifespan)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "agent-tools"}
