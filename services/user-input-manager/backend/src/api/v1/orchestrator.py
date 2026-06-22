"""Orchestrator proxy router.

Forwards requests to the Orchestrator Service on behalf of the authenticated
user, injecting the user's Bearer token so the Orchestrator can validate it.

All orchestrator endpoints are exposed under /api/v1/orchestrator/* —
the frontend never calls the Orchestrator directly.
"""

from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from src.api.dependencies import get_current_user
from src.core.config import get_settings
from src.models.models import User

logger = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter(prefix="/orchestrator", tags=["orchestrator"])


async def _proxy(
    method: str,
    path: str,
    user_token: str,
    body: dict | None = None,
    params: dict | None = None,
) -> JSONResponse:
    """Forward one request to the Orchestrator Service."""
    url = f"{settings.orchestrator_base_url.rstrip('/')}{path}"
    headers = {"Authorization": f"Bearer {user_token}"}

    try:
        async with httpx.AsyncClient(timeout=settings.orchestrator_timeout_seconds) as c:
            resp = await c.request(
                method,
                url,
                headers=headers,
                json=body,
                params={k: v for k, v in (params or {}).items() if v is not None},
            )
    except httpx.ConnectError:
        raise HTTPException(503, "Orchestrator Service unavailable")
    except httpx.TimeoutException:
        raise HTTPException(504, "Orchestrator Service timed out")

    return JSONResponse(status_code=resp.status_code, content=resp.json() if resp.content else None)


def _token(request: Request) -> str:
    auth = request.headers.get("Authorization", "")
    return auth.removeprefix("Bearer ").strip()


# ---------------------------------------------------------------------------
# Pending tickets (from TM via Orchestrator)
# ---------------------------------------------------------------------------


@router.get("/pending-tickets")
async def pending_tickets(
    request: Request,
    project_id: str | None = Query(default=None),
    _: User = Depends(get_current_user),
):
    return await _proxy(
        "GET", "/api/v1/jobs/pending-tickets", _token(request), params={"project_id": project_id}
    )


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------


@router.post("/jobs/trigger", status_code=201)
async def trigger_job(request: Request, _: User = Depends(get_current_user)):
    body = await request.json()
    return await _proxy("POST", "/api/v1/jobs/trigger", _token(request), body=body)


@router.get("/jobs")
async def list_jobs(
    request: Request,
    status: str | None = Query(default=None),
    ticket_id: str | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    _: User = Depends(get_current_user),
):
    return await _proxy(
        "GET",
        "/api/v1/jobs",
        _token(request),
        params={"status": status, "ticket_id": ticket_id, "offset": offset, "limit": limit},
    )


@router.get("/jobs/{job_id}")
async def get_job(request: Request, job_id: str, _: User = Depends(get_current_user)):
    return await _proxy("GET", f"/api/v1/jobs/{job_id}", _token(request))


# ---------------------------------------------------------------------------
# Audit trail
# ---------------------------------------------------------------------------


@router.get("/audit/{ticket_id}")
async def audit_trail(
    request: Request,
    ticket_id: str,
    offset: int = Query(default=0),
    limit: int = Query(default=100),
    _: User = Depends(get_current_user),
):
    return await _proxy(
        "GET",
        f"/api/v1/audit/{ticket_id}",
        _token(request),
        params={"offset": offset, "limit": limit},
    )


# ---------------------------------------------------------------------------
# Project memory & ADRs (read-only)
# ---------------------------------------------------------------------------


@router.get("/memory/{project_id}")
async def project_memory(request: Request, project_id: str, _: User = Depends(get_current_user)):
    return await _proxy("GET", f"/api/v1/memory/{project_id}", _token(request))


@router.get("/memory/{project_id}/adrs")
async def project_adrs(
    request: Request,
    project_id: str,
    status: str = Query(default="accepted"),
    _: User = Depends(get_current_user),
):
    return await _proxy(
        "GET", f"/api/v1/memory/{project_id}/adrs", _token(request), params={"status": status}
    )
