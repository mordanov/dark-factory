"""Poller — fetches assigned tickets from Orchestrator."""

from __future__ import annotations

from dataclasses import dataclass, field
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
    tags: list[str] = field(default_factory=list)
    required_capabilities: list[str] = field(default_factory=list)


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
        tags = list(t.get("tags") or [])
        result.append(
            TmTicket(
                id=ticket_id,
                project_id=t.get("project_id", ""),
                assigned_agent=t.get("assigned_agent", ""),
                fsm_status=t.get("fsm_status", ""),
                ticket_type=t.get("ticket_type", ""),
                title=t.get("title", ""),
                description=t.get("description", ""),
                tags=tags,
                required_capabilities=derive_required_capabilities(t.get("fsm_status", ""), tags),
            )
        )
    return result


# Mapping from FSM state to base required capabilities.
# Tags that match known capability names are added as extras.
_STATE_CAPABILITIES: dict[str, list[str]] = {
    "backend_development": ["python_backend"],
    "frontend_development": ["typescript_frontend"],
    "security_review": ["security_assessment"],
    "architecture_review": ["system_design"],
    "code_review": ["code_review_skill"],
    "testing": ["automated_testing"],
    "devops": ["ci_cd"],
}

_KNOWN_CAPABILITY_NAMES: frozenset[str] = frozenset(
    cap for caps in _STATE_CAPABILITIES.values() for cap in caps
)


def derive_required_capabilities(fsm_status: str, tags: list[str]) -> list[str]:
    """Map FSM state + ticket tags to required capability names."""
    base = list(_STATE_CAPABILITIES.get(fsm_status, []))
    tag_extras = [t for t in tags if t in _KNOWN_CAPABILITY_NAMES]
    seen: set[str] = set()
    result: list[str] = []
    for cap in base + tag_extras:
        if cap not in seen:
            seen.add(cap)
            result.append(cap)
    return result
