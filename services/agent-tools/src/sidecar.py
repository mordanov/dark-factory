"""Minimal FastAPI sidecar for agent-tools health endpoint and auth adapter."""
from __future__ import annotations

from fastapi import FastAPI

from src.core.auth_adapter import AuthAdapter
from src.config import get_settings

app = FastAPI(title="agent-tools-sidecar", docs_url=None, redoc_url=None)

_settings = get_settings()
_adapter = AuthAdapter(_settings)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "agent-tools"}
