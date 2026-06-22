"""Memory and ADR endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from src.api.dependencies import MongoDep, UserDep
from src.core.exceptions import ConflictError, NotFoundError
from src.repositories.memory_repo import MemoryRepository
from src.schemas.schemas import (
    AdrCreate,
    AdrCreatedResponse,
    AdrListResponse,
    AdrStatusResponse,
    AdrStatusUpdate,
    AdrSummary,
    MemoryResponse,
)

router = APIRouter()


@router.get("/memory/{project_id}", response_model=MemoryResponse)
async def get_memory(
    project_id: str,
    mongo: MongoDep,
    _user: UserDep,
) -> MemoryResponse:
    repo = MemoryRepository(mongo)
    doc = await repo.get_memory(project_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Project memory not found")
    updated_at = doc.get("updated_at", "")
    if isinstance(updated_at, str):
        updated_at = datetime.fromisoformat(updated_at)
    return MemoryResponse(
        project_id=doc["_id"],
        content=doc["content"],
        version=doc["version"],
        last_ticket_id=doc.get("last_ticket_id", ""),
        updated_at=updated_at,
    )


@router.get("/memory/{project_id}/adrs", response_model=AdrListResponse)
async def list_adrs(
    project_id: str,
    mongo: MongoDep,
    _user: UserDep,
    status: str | None = Query(default="accepted"),
) -> AdrListResponse:
    repo = MemoryRepository(mongo)
    adrs = await repo.get_adrs(project_id, status_filter=status or "accepted")
    items = [
        AdrSummary(
            id=a["_id"],
            title=a.get("title", ""),
            status=a.get("status", ""),
            summary=a.get("summary", ""),
            ticket_id=a.get("ticket_id", ""),
            created_at=datetime.fromisoformat(a["created_at"])
            if isinstance(a.get("created_at"), str)
            else a.get("created_at", datetime.utcnow()),
        )
        for a in adrs
    ]
    return AdrListResponse(adrs=items)


@router.post(
    "/memory/{project_id}/adrs",
    response_model=AdrCreatedResponse,
    status_code=201,
)
async def create_adr(
    project_id: str,
    body: AdrCreate,
    mongo: MongoDep,
    _user: UserDep,
) -> AdrCreatedResponse:
    repo = MemoryRepository(mongo)
    adr_id = await repo.create_adr(
        project_id,
        {
            "title": body.title,
            "summary": body.summary,
            "content": body.content,
            "ticket_id": body.ticket_id,
        },
    )
    return AdrCreatedResponse(adr_id=adr_id)


@router.patch(
    "/memory/{project_id}/adrs/{adr_id}/status",
    response_model=AdrStatusResponse,
)
async def update_adr_status(
    project_id: str,
    adr_id: str,
    body: AdrStatusUpdate,
    mongo: MongoDep,
    _user: UserDep,
) -> AdrStatusResponse:
    repo = MemoryRepository(mongo)
    try:
        result = await repo.update_adr_status(project_id, adr_id, body.status)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return AdrStatusResponse(**result)
