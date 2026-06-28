"""Worker lifecycle API — POST /api/v1/workers/* and GET /api/v1/workers."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth_adapter import KeycloakValidator, UnauthorizedError, UserClaims
from src.db.session import get_db
from src.schemas.schemas import (
    DrainRequest,
    DrainResponse,
    HeartbeatRequest,
    HeartbeatResponse,
    WorkerListResponse,
    WorkerRecord,
    WorkerRegisterRequest,
    WorkerRegisterResponse,
)
from src.services.worker_service import AgentWorkerService

logger = structlog.get_logger(__name__)
router = APIRouter()
security = HTTPBearer()
_adapter = KeycloakValidator()


async def _verify_token(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> UserClaims:
    try:
        return await _adapter.verify(credentials.credentials)
    except UnauthorizedError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@router.post("/workers/register", response_model=WorkerRegisterResponse, status_code=201)
async def register_worker(
    body: WorkerRegisterRequest,
    db: AsyncSession = Depends(get_db),
    _: UserClaims = Depends(_verify_token),
) -> WorkerRegisterResponse:
    svc = AgentWorkerService(db)
    try:
        result = await svc.register_worker(
            role_id=body.role_id,
            version=body.version,
            capabilities_snapshot=body.capabilities_snapshot,
        )
        await db.commit()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return WorkerRegisterResponse(**result)


@router.post("/workers/{role_id}/heartbeat", response_model=HeartbeatResponse)
async def worker_heartbeat(
    role_id: str,
    body: HeartbeatRequest,
    db: AsyncSession = Depends(get_db),
    _: UserClaims = Depends(_verify_token),
) -> HeartbeatResponse:
    svc = AgentWorkerService(db)
    try:
        result = await svc.record_heartbeat(
            worker_id=body.worker_id,
            role_id=role_id,
            status=body.status,
        )
        await db.commit()
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return HeartbeatResponse(**result)


@router.post("/workers/{role_id}/drain", response_model=DrainResponse)
async def drain_worker(
    role_id: str,
    body: DrainRequest,
    db: AsyncSession = Depends(get_db),
    _: UserClaims = Depends(_verify_token),
) -> DrainResponse:
    svc = AgentWorkerService(db)
    try:
        result = await svc.drain_worker(worker_id=body.worker_id, role_id=role_id)
        await db.commit()
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return DrainResponse(**result)


@router.get("/workers", response_model=WorkerListResponse)
async def list_workers(
    status: str | None = None,
    role_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    _: UserClaims = Depends(_verify_token),
) -> WorkerListResponse:
    svc = AgentWorkerService(db)
    workers = await svc.list_workers(status_filter=status, role_id_filter=role_id)
    items = [WorkerRecord.model_validate(w) for w in workers]
    return WorkerListResponse(workers=items, total=len(items))
