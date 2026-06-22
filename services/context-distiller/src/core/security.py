"""JWT validation (verify only — never issues tokens)."""

from __future__ import annotations

from fastapi import HTTPException, status
from jose import JWTError, jwt

from src.core.config import get_settings


def decode_token(token: str) -> dict:
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        return payload
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def verify_access_token(token: str) -> dict:
    """Decode and verify a JWT, propagating JWTError on failure."""
    settings = get_settings()
    return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
