"""Auth adapter — thin seam between FastAPI auth dependency and the validation backend."""
from __future__ import annotations

from jose import JWTError, jwt

from src.config import Settings


class AuthAdapter:
    """Validates incoming JWT tokens.

    Reads AUTH_MODE from settings:
      local    — validates with local SECRET_KEY (current behaviour, unchanged)
      keycloak — validates against KEYCLOAK_JWKS_URL (not implemented in this phase)
    """

    def __init__(self, settings: Settings) -> None:
        if settings.auth_mode not in ("local", "keycloak"):
            raise ValueError(f"Unknown AUTH_MODE: {settings.auth_mode!r}")
        self.settings = settings

    async def verify(self, token: str) -> dict:
        """Return decoded JWT claims or raise.

        Raises:
            jose.JWTError — invalid or expired token (AUTH_MODE=local)
            NotImplementedError — AUTH_MODE=keycloak (not yet implemented)
            ValueError — unrecognised AUTH_MODE value (raised at init)
        """
        if self.settings.auth_mode == "keycloak":
            raise NotImplementedError("Keycloak validation not implemented")
        return jwt.decode(token, self.settings.jwt_secret_key, algorithms=[self.settings.jwt_algorithm])
