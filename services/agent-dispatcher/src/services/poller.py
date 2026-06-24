"""Poller — fetches assigned tickets from Orchestrator."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import httpx
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.core.keycloak_client import get_kc_client
from src.repositories.run_repo import AgentRunRepository

logger = structlog.get_logger(__name__)


@dataclass
class TmTicket:
    id: str
    project_id: str
    assigned_agent: str
    fsm_status: str
    ticket_type: str
    title: str
    description: str


async def poll_once(db: AsyncSession) -> list[TmTicket]:
    """Poll Orchestrator for assigned tickets; filter out already-running ones."""
    settings = get_settings()
    auth_headers = await get_kc_client().async_auth_headers()
    url = f"{settings.orchestrator_base_url}/api/v1/jobs/pending-tickets"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=auth_headers)
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        logger.warning("Orchestrator poll failed", error=str(exc))
        return []

    raw_tickets = data.get("tickets", [])
    assigned = [t for t in raw_tickets if t.get("assigned_agent")]

    repo = AgentRunRepository(db)
    result: list[TmTicket] = []
    for t in assigned:
        ticket_id = t.get("id", "")
        if await repo.has_running(ticket_id):
            continue
        result.append(
            TmTicket(
                id=ticket_id,
                project_id=t.get("project_id", ""),
                assigned_agent=t.get("assigned_agent", ""),
                fsm_status=t.get("fsm_status", ""),
                ticket_type=t.get("ticket_type", ""),
                title=t.get("title", ""),
                description=t.get("description", ""),
            )
        )
    return result
