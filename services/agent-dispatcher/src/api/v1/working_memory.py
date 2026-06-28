"""Working memory API — GET/POST /api/v1/working-memory/{ticket_id}."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth_adapter import KeycloakValidator, UnauthorizedError, UserClaims
from src.db.session import get_db
from src.schemas.schemas import (
    WorkingMemoryEntryCreate,
    WorkingMemoryEntryResponse,
    WorkingMemoryListResponse,
)
from src.services.working_memory_service import WorkingMemoryService

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


@router.get(
    "/working-memory/{ticket_id}",
    response_model=WorkingMemoryListResponse,
)
async def list_working_memory(
    ticket_id: str,
    run_id: str | None = Query(default=None, description="Caller's run_id for cross-ticket isolation check"),
    author_role_id: str | None = Query(default=None),
    entry_type: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    _: UserClaims = Depends(_verify_token),
) -> WorkingMemoryListResponse:
    import uuid as _uuid

    svc = WorkingMemoryService(db)
    parsed_run_id = None
    if run_id is not None:
        try:
            parsed_run_id = _uuid.UUID(run_id)
        except ValueError:
            raise HTTPException(status_code=422, detail="run_id must be a valid UUID")

    try:
        entries = await svc.list_for_ticket(
            ticket_id=ticket_id,
            requester_run_id=parsed_run_id,
            author_role_id=author_role_id,
            entry_type=entry_type,
            limit=limit + 1,  # fetch one extra to determine has_more
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    has_more = len(entries) > limit
    page = entries[:limit]
    return WorkingMemoryListResponse(
        ticket_id=ticket_id,
        entries=[WorkingMemoryEntryResponse.model_validate(e) for e in page],
        total=len(page),
        has_more=has_more,
    )


@router.post(
    "/working-memory/{ticket_id}",
    response_model=WorkingMemoryEntryResponse,
    status_code=201,
)
async def append_working_memory(
    ticket_id: str,
    body: WorkingMemoryEntryCreate,
    db: AsyncSession = Depends(get_db),
    _: UserClaims = Depends(_verify_token),
) -> WorkingMemoryEntryResponse:
    svc = WorkingMemoryService(db)

    try:
        entry = await svc.append(
            ticket_id=ticket_id,
            run_id=body.run_id,
            author_role_id=body.author_role_id,
            entry_type=body.entry_type,
            content=body.content,
            tags=body.tags,
        )
        await db.commit()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    return WorkingMemoryEntryResponse.model_validate(entry)
