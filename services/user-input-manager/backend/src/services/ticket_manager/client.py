"""Ticket Manager API client.

Wraps the external ticket-manager REST API.  A single service account
(credentials from settings) is used for all calls — individual user
attribution is stored in our own DB.

See api-endpoints-agent-playbook.md for the full contract.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from src.core.config import get_settings
from src.core.exceptions import UpstreamError
from src.core.keycloak_client import get_kc_client

logger = logging.getLogger(__name__)
settings = get_settings()

NEEDS_ESTIMATION_TAG = "needs-estimation"


class TicketManagerClient:
    """Stateless async client — create per-request or as a singleton.

    The token is acquired on first use and stored for the lifetime of the
    instance (suitable for a request-scoped dependency or a long-lived
    singleton with token refresh logic).
    """

    def __init__(self) -> None:
        self._base = str(settings.ticket_manager_base_url).rstrip("/")
        self._timeout = settings.ticket_manager_timeout_seconds

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _headers(self) -> dict[str, str]:
        return await get_kc_client().async_auth_headers()

    async def _request(self, method: str, path: str, **kwargs) -> Any:
        """Make an authenticated request; retry once if 401."""
        headers = await self._headers()
        url = f"{self._base}{path}"
        async with httpx.AsyncClient(timeout=self._timeout) as c:
            resp = await c.request(method, url, headers=headers, **kwargs)
            if resp.status_code == 401:
                headers = await self._headers()
                resp = await c.request(method, url, headers=headers, **kwargs)

        if resp.status_code >= 400:
            logger.warning("TM API %s %s → %s: %s", method, path, resp.status_code, resp.text[:300])
            raise UpstreamError(f"Ticket Manager error {resp.status_code}: {resp.text[:200]}")
        if resp.status_code == 204:
            return None
        return resp.json()

    # ------------------------------------------------------------------
    # Projects
    # ------------------------------------------------------------------

    async def list_projects(self) -> list[dict]:
        data = await self._request("GET", "/api/projects")
        # normalise: API may return a list or {"projects": [...]}
        if isinstance(data, list):
            return data
        return data.get("projects", data.get("data", []))

    async def get_project(self, project_id: str) -> dict:
        return await self._request("GET", f"/api/projects/{project_id}")

    async def create_project(self, name: str, description: str = "") -> dict:
        return await self._request(
            "POST",
            "/api/projects",
            json={"name": name, "description": description},
        )

    # ------------------------------------------------------------------
    # Tickets
    # ------------------------------------------------------------------

    async def list_tickets(self, project_id: str) -> list[dict]:
        data = await self._request("GET", f"/api/projects/{project_id}/tickets")
        if isinstance(data, list):
            return data
        return data.get("tickets", data.get("data", []))

    async def create_ticket(
        self,
        project_id: str,
        title: str,
        description: str,
        ticket_type: str = "other",
    ) -> dict:
        """Create a ticket with needs-estimation tag in both tag field and description prefix."""
        body = {
            "title": title,
            "description": f"[needs-estimation]\n\n{description}",
            "type": ticket_type,
            "tags": [NEEDS_ESTIMATION_TAG],
        }
        return await self._request(
            "POST",
            f"/api/projects/{project_id}/tickets",
            json=body,
        )

    # ------------------------------------------------------------------
    # Context building (for LLM prompt)
    # ------------------------------------------------------------------

    async def build_project_context(self, project_id: str) -> str:
        """Return a compact text block summarising existing tickets in a project."""
        tickets = await self.list_tickets(project_id)
        if not tickets:
            return "No existing tickets in this project."

        max_tickets = settings.ticket_manager_context_max_tickets
        max_chars = settings.ticket_manager_context_max_chars

        lines: list[str] = ["Existing tickets in this project:"]
        for t in tickets[:max_tickets]:
            tid = t.get("id", "?")
            title = t.get("title", "(no title)")
            status = t.get("status", "")
            t_type = t.get("type", "")
            desc = (t.get("description") or "")[:200]
            lines.append(f"- [{tid}] {title} ({t_type}, {status}): {desc}")

        context = "\n".join(lines)
        return context[:max_chars]


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------

_client_singleton: TicketManagerClient | None = None


def get_ticket_manager_client() -> TicketManagerClient:
    """Return a process-level singleton client (token cached between requests)."""
    global _client_singleton
    if _client_singleton is None:
        _client_singleton = TicketManagerClient()
    return _client_singleton
