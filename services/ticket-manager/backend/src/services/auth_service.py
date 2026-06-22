import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.security import create_access_token, verify_password
from src.models.refresh_token import RefreshToken
from src.models.user import User
from src.schemas.auth import TokenResponse

_REFRESH_TOKEN_EXPIRE_DAYS = 30


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


async def login(session: AsyncSession, email: str, password: str) -> TokenResponse:
    result = await session.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if user is None or not verify_password(password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    if user.blocked_at is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account has been blocked. Contact an administrator.",
        )

    access_token = create_access_token(str(user.id), user.role.value)

    raw_refresh = secrets.token_urlsafe(64)
    token_hash = _hash_token(raw_refresh)
    expires_at = datetime.now(UTC) + timedelta(days=_REFRESH_TOKEN_EXPIRE_DAYS)

    rt = RefreshToken(user_id=user.id, token_hash=token_hash, expires_at=expires_at)
    session.add(rt)
    await session.commit()

    return TokenResponse(
        access_token=access_token,
        expires_in=settings.access_token_expire_minutes * 60,
        refresh_token=raw_refresh,
    )


async def refresh(session: AsyncSession, raw_refresh_token: str) -> TokenResponse:
    token_hash = _hash_token(raw_refresh_token)
    result = await session.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    rt = result.scalar_one_or_none()

    if rt is None or rt.revoked_at is not None or rt.expires_at < datetime.now(UTC):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token is invalid or expired",
        )

    user = await session.get(User, rt.user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    access_token = create_access_token(str(user.id), user.role.value)
    await session.commit()

    return TokenResponse(
        access_token=access_token,
        expires_in=settings.access_token_expire_minutes * 60,
    )


async def logout(session: AsyncSession, raw_refresh_token: str) -> None:
    token_hash = _hash_token(raw_refresh_token)
    result = await session.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    rt = result.scalar_one_or_none()
    if rt is not None and rt.revoked_at is None:
        rt.revoked_at = datetime.now(UTC)
        await session.commit()
