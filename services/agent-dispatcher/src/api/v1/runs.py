"""GET /api/v1/runs — run history endpoints."""

from __future__ import annotations

import uuid
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth_adapter import AuthAdapter
from src.core.config import get_settings
from src.db.session import get_db
from src.repositories.run_repo import AgentRunRepository
from src.schemas.schemas import AgentRunListResponse, AgentRunResponse

logger = structlog.get_logger(__name__)
router = APIRouter()
security = HTTPBearer()


async def _verify_token(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    settings = get_settings()
    adapter = AuthAdapter(settings)
    try:
        return await adapter.verify(credentials.credentials)
    except (JWTError, NotImplementedError) as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@router.get("/runs", response_model=AgentRunListResponse)
async def list_runs(
    ticket_id: str | None = Query(None),
    status: str | None = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(_verify_token),
) -> AgentRunListResponse:
    repo = AgentRunRepository(db)
    runs, total = await repo.list_all(
        ticket_id=ticket_id, status=status, offset=offset, limit=limit
    )
    items = []
    for run in runs:
        resp = AgentRunResponse.model_validate(run)
        resp.raw_output = None
        items.append(resp)
    return AgentRunListResponse(items=items, total=total)


@router.get("/runs/{run_id}", response_model=AgentRunResponse)
async def get_run(
    run_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(_verify_token),
) -> AgentRunResponse:
    repo = AgentRunRepository(db)
    run = await repo.get_by_id(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return AgentRunResponse.model_validate(run)
