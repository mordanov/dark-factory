"""Ticket Manager API client."""
from __future__ import annotations
import logging

import httpx

from src.core.config import get_settings
from src.core.exceptions import UpstreamError

logger = logging.getLogger(__name__)


class TMClient:
    def __init__(self) -> None:
        self._settings = get_settings()
        self._token: str | None = None
        self._client = httpx.AsyncClient(
            base_url=str(self._settings.ticket_manager_base_url),
            timeout=30.0,
        )

    async def _ensure_token(self) -> None:
        if self._token:
            return
        resp = await self._client.post(
            "/api/v1/auth/login",
            json={
                "email": self._settings.ticket_manager_service_email,
                "password": self._settings.ticket_manager_service_password,
            },
        )
        if resp.status_code != 200:
            raise UpstreamError(
                f"TM login failed: {resp.status_code} {resp.text[:200]}"
            )
        self._token = resp.json()["access_token"]

    def _auth_headers(self) -> dict:
        return {"Authorization": f"Bearer {self._token}"}

    async def get_ticket(self, ticket_id: str) -> dict:
        await self._ensure_token()
        resp = await self._client.get(
            f"/api/v1/tickets/{ticket_id}",
            headers=self._auth_headers(),
        )
        if resp.status_code == 404:
            raise UpstreamError(f"Ticket {ticket_id} not found in TM")
        if not resp.is_success:
            raise UpstreamError(
                f"TM get_ticket failed: {resp.status_code} {resp.text[:200]}"
            )
        return resp.json()

    async def get_ticket_events(self, ticket_id: str) -> list[dict]:
        await self._ensure_token()
        resp = await self._client.get(
            f"/api/v1/tickets/{ticket_id}/events",
            headers=self._auth_headers(),
        )
        if not resp.is_success:
            raise UpstreamError(
                f"TM get_ticket_events failed: {resp.status_code} {resp.text[:200]}"
            )
        data = resp.json()
        return data.get("items", data) if isinstance(data, dict) else data

    async def aclose(self) -> None:
        await self._client.aclose()
