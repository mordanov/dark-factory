"""Authentication service — login, token refresh, current-user lookup."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ForbiddenError, UnauthorizedError
from src.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_access_token,
    verify_password,
    verify_refresh_token,
)
from src.models.models import User
from src.repositories.user_repo import UserRepository
from src.schemas.schemas import TokenResponse


class AuthService:
    def __init__(self, db: AsyncSession) -> None:
        self._repo = UserRepository(db)

    async def login(self, email: str, password: str) -> TokenResponse:
        user = await self._repo.get_by_email(email)
        if not user or not verify_password(password, user.password_hash):
            raise UnauthorizedError("Invalid credentials")
        if not user.is_active:
            raise ForbiddenError("Account is disabled")
        return TokenResponse(
            access_token=create_access_token(str(user.id), user.is_admin),
            refresh_token=create_refresh_token(str(user.id)),
        )

    async def refresh(self, refresh_token: str) -> TokenResponse:
        try:
            payload = verify_refresh_token(refresh_token)
        except Exception as exc:
            raise UnauthorizedError("Invalid refresh token") from exc
        user = await self._repo.get_by_id(payload["sub"])
        if not user or not user.is_active:
            raise UnauthorizedError("User not found or inactive")
        return TokenResponse(
            access_token=create_access_token(str(user.id), user.is_admin),
            refresh_token=create_refresh_token(str(user.id)),
        )

    async def get_current_user(self, token: str) -> User:
        try:
            payload = verify_access_token(token)
        except Exception as exc:
            raise UnauthorizedError("Invalid access token") from exc
        user = await self._repo.get_by_id(payload["sub"])
        if not user:
            raise UnauthorizedError("User not found")
        if not user.is_active:
            raise ForbiddenError("Account is disabled")
        return user
