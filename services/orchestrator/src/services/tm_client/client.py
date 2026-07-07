"""Ticket Manager API client — orchestrator edition.

Includes calls to the extended FSM endpoints described in
ticket-manager-extensions.md.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from src.core.config import get_settings
from src.core.exceptions import UpstreamError
from src.core.keycloak_client import get_kc_client
from src.schemas.schemas import TmTicket

logger = logging.getLogger(__name__)
settings = get_settings()


class TicketManagerClient:
    def __init__(self) -> None:
        self._base = str(settings.ticket_manager_base_url).rstrip("/")
        self._timeout = settings.ticket_manager_timeout_seconds

    async def _headers(self) -> dict:
        return await get_kc_client().async_auth_headers()

    async def _request(self, method: str, path: str, **kwargs) -> Any:
        headers = await self._headers()
        url = f"{self._base}{path}"
        async with httpx.AsyncClient(timeout=self._timeout) as c:
            resp = await c.request(method, url, headers=headers, **kwargs)
            if resp.status_code == 401:
                headers = await self._headers()
                resp = await c.request(method, url, headers=headers, **kwargs)
        if resp.status_code >= 400:
            raise UpstreamError(f"TM {method} {path} → {resp.status_code}: {resp.text[:200]}")
        if resp.status_code == 204:
            return None
        return resp.json()

    # ------------------------------------------------------------------
    # Polling — extended endpoints
    # ------------------------------------------------------------------

    async def get_pending_tickets(
        self, project_id: str | None = None, limit: int = 50
    ) -> list[dict]:
        """GET /api/orchestrator/pending — tickets awaiting orchestrator processing."""
        params: dict = {"limit": limit}
        if project_id:
            params["project_id"] = project_id
        data = await self._request("GET", "/api/v1/orchestrator/pending", params=params)
        return data.get("tickets", data if isinstance(data, list) else [])

    async def get_ticket_full(self, project_id: str, ticket_id: str) -> dict:
        """GET /api/projects/{project_id}/tickets/{ticket_id}/full"""
        return await self._request("GET", f"/api/v1/projects/{project_id}/tickets/{ticket_id}/full")

    # ------------------------------------------------------------------
    # FSM state management — extended endpoints
    # ------------------------------------------------------------------

    async def update_fsm(
        self,
        project_id: str,
        ticket_id: str,
        *,
        fsm_status: str | None = None,
        blocked_reason: str | None = None,
        assigned_agent: str | None = None,
        brainstorm_round: int | None = None,
        orchestrator_errors: list[str] | None = None,
        clear_override: bool = False,
    ) -> dict:
        """PATCH /api/v1/projects/{project_id}/tickets/{ticket_id}/fsm"""
        body: dict = {}
        if fsm_status is not None:
            body["fsm_status"] = fsm_status
        if blocked_reason is not None:
            body["blocked_reason"] = blocked_reason
        if assigned_agent is not None:
            body["assigned_agent"] = assigned_agent
        if brainstorm_round is not None:
            body["brainstorm_round"] = brainstorm_round
        if orchestrator_errors is not None:
            body["orchestrator_errors"] = orchestrator_errors
        if clear_override:
            body["override"] = False
            body["override_reason"] = None
        return await self._request(
            "PATCH", f"/api/v1/projects/{project_id}/tickets/{ticket_id}/fsm", json=body
        )

    async def manage_tags(
        self, project_id: str, ticket_id: str, *, add: list[str] = (), remove: list[str] = ()
    ) -> dict:
        """POST /api/v1/projects/{project_id}/tickets/{ticket_id}/tags"""
        return await self._request(
            "POST",
            f"/api/v1/projects/{project_id}/tickets/{ticket_id}/tags",
            json={"add": list(add), "remove": list(remove)},
        )

    async def get_fsm_status_batch(self, ticket_ids: list[str]) -> dict[str, dict]:
        """POST /api/v1/tickets/fsm-status-batch"""
        data = await self._request(
            "POST", "/api/v1/tickets/fsm-status-batch", json={"ticket_ids": ticket_ids}
        )
        return data.get("statuses", {})

    # ------------------------------------------------------------------
    # Standard endpoints
    # ------------------------------------------------------------------

    async def list_projects(self) -> list[dict]:
        data = await self._request("GET", "/api/v1/projects")
        return data if isinstance(data, list) else data.get("projects", [])

    async def list_tickets(self, project_id: str) -> list[dict]:
        data = await self._request("GET", f"/api/v1/projects/{project_id}/tickets")
        return data if isinstance(data, list) else data.get("tickets", [])


_client: TicketManagerClient | None = None


def get_tm_client() -> TicketManagerClient:
    global _client
    if _client is None:
        _client = TicketManagerClient()
    return _client
