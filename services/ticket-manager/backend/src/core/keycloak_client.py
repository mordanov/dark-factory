"""Keycloak Client Credentials token provider for service-to-service calls."""

from __future__ import annotations

import asyncio
import time

import httpx
import structlog

from src.core.config import get_settings

log = structlog.get_logger(__name__)


class UpstreamError(Exception):
    """Raised when Keycloak token endpoint returns an error."""


class KeycloakServiceClient:
    def __init__(
        self,
        keycloak_base_url: str,
        realm: str,
        client_id: str,
        client_secret: str,
    ) -> None:
        self._token_url = (
            f"{keycloak_base_url.rstrip('/')}/realms/{realm}/protocol/openid-connect/token"
        )
        self._client_id = client_id
        self._client_secret = client_secret
        self._token: str | None = None
        self._expires_at: float = 0.0
        self._lock = asyncio.Lock()

    async def get_token(self) -> str:
        async with self._lock:
            if self._token is not None and time.monotonic() < self._expires_at - 30:
                return self._token
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.post(
                        self._token_url,
                        data={
                            "grant_type": "client_credentials",
                            "client_id": self._client_id,
                            "client_secret": self._client_secret,
                        },
                    )
            except Exception as exc:
                raise UpstreamError(f"Keycloak token request failed: {exc}") from exc
            if resp.status_code != 200:
                raise UpstreamError(
                    f"Keycloak returned {resp.status_code} on token endpoint"
                    f" for client {self._client_id!r}"
                )
            data = resp.json()
            self._token = data["access_token"]
            self._expires_at = time.monotonic() + int(data.get("expires_in", 300))
            log.debug("keycloak_token_refreshed", client_id=self._client_id)
            return self._token

    async def async_auth_headers(self) -> dict[str, str]:
        token = await self.get_token()
        return {"Authorization": f"Bearer {token}"}


_kc_client: KeycloakServiceClient | None = None


def get_kc_client() -> KeycloakServiceClient:
    global _kc_client
    if _kc_client is None:
        settings = get_settings()
        _kc_client = KeycloakServiceClient(
            keycloak_base_url=settings.keycloak_base_url,
            realm=settings.keycloak_realm,
            client_id=settings.keycloak_client_id,
            client_secret=settings.keycloak_client_secret,
        )
    return _kc_client
