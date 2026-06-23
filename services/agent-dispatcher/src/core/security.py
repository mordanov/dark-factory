"""JWT generation and verification for Agent Dispatcher."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from jose import JWTError, jwt

from src.core.config import get_settings

settings = get_settings()


def create_service_token() -> str:
    """Generate a short-lived service JWT for outbound calls."""
    expire = datetime.now(UTC) + timedelta(hours=settings.service_jwt_expire_hours)
    payload = {
        "sub": "service:agent-dispatcher",
        "exp": expire,
        "type": "access",
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def verify_access_token(token: str) -> dict[str, Any]:
    """Decode and validate an incoming Bearer token."""
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:
        raise exc
    if payload.get("type") != "access":
        raise JWTError("Not an access token")
    return payload
