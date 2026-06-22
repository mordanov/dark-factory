"""JWT verification — accepts tokens issued by Prompt Studio backend."""

from __future__ import annotations

from typing import Any

from jose import JWTError, jwt

from src.core.config import get_settings

settings = get_settings()


def verify_access_token(token: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:
        raise exc
    if payload.get("type") != "access":
        raise JWTError("Not an access token")
    return payload
