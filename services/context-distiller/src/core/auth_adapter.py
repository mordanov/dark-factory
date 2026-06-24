"""Auth adapter — KeycloakValidator for JWT validation."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import httpx
import structlog
from jose import JWTError, jwt

from src.core.config import get_settings

log = structlog.get_logger(__name__)


@dataclass
class UserClaims:
    sub: str
    email: str
    preferred_username: str
    roles: list[str] = field(default_factory=list)

    @property
    def is_admin(self) -> bool:
        return "administrator" in self.roles


class UnauthorizedError(Exception):
    """Raised when token validation fails."""


class KeycloakValidator:
    def __init__(self) -> None:
        self._jwks: dict | None = None
        self._jwks_fetched_at: float = 0.0
        self._jwks_ttl: float = 300.0

    async def verify(self, token: str) -> UserClaims:
        settings = get_settings()
        if settings.auth_mode not in ("local", "keycloak"):
            raise ValueError(f"Unknown AUTH_MODE: {settings.auth_mode!r}")
        try:
            if settings.auth_mode == "local":
                payload = jwt.decode(token, settings.test_jwt_secret, algorithms=["HS256"])
            else:
                jwks = await self._get_jwks(settings)
                payload = jwt.decode(
                    token, jwks, algorithms=["RS256"], options={"verify_aud": False}
                )
        except JWTError as exc:
            raise UnauthorizedError(str(exc)) from exc
        return self._extract_claims(payload)

    async def _get_jwks(self, settings) -> dict:
        now = time.monotonic()
        if self._jwks is not None and (now - self._jwks_fetched_at) < self._jwks_ttl:
            return self._jwks
        realm_path = f"{settings.keycloak_base_url}/realms/{settings.keycloak_realm}"
        url = f"{realm_path}/protocol/openid-connect/certs"
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                self._jwks = resp.json()
                self._jwks_fetched_at = now
        except Exception as exc:
            if self._jwks is not None:
                log.warning("jwks_refresh_failed_using_stale_cache", error=str(exc))
            else:
                raise UnauthorizedError(f"Failed to fetch JWKS: {exc}") from exc
        return self._jwks  # type: ignore[return-value]

    def _extract_claims(self, payload: dict) -> UserClaims:
        sub = payload.get("sub", "")
        email = payload.get("email", "")
        preferred_username = payload.get("preferred_username") or email
        roles = payload.get("realm_access", {}).get("roles", [])
        is_service_account = bool(payload.get("client_id"))
        if not sub or (not email and not is_service_account):
            raise UnauthorizedError("Token missing required claims (sub, email)")
        if not email:
            email = f"{preferred_username}@service.internal"
        return UserClaims(sub=sub, email=email, preferred_username=preferred_username, roles=roles)


async def prefetch_jwks() -> None:
    """Call at startup; raises RuntimeError if keycloak mode and JWKS unreachable."""
    settings = get_settings()
    if settings.auth_mode != "keycloak":
        return
    validator = KeycloakValidator()
    try:
        await validator._get_jwks(settings)
    except Exception as exc:
        raise RuntimeError(f"Keycloak JWKS unreachable at startup: {exc}") from exc
