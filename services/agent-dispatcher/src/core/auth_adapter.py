"""Auth adapter — seam between FastAPI auth dependency and validation backend."""

from __future__ import annotations

from src.core.config import Settings
from src.core.security import verify_access_token


class AuthAdapter:
    """Validates incoming JWT tokens.

    AUTH_MODE=local    — validates with local SECRET_KEY
    AUTH_MODE=keycloak — not implemented this phase
    """

    def __init__(self, settings: Settings) -> None:
        if settings.auth_mode not in ("local", "keycloak"):
            raise ValueError(f"Unknown AUTH_MODE: {settings.auth_mode!r}")
        self.settings = settings

    async def verify(self, token: str) -> dict:
        if self.settings.auth_mode == "keycloak":
            raise NotImplementedError("Keycloak validation not implemented")
        return verify_access_token(token)
