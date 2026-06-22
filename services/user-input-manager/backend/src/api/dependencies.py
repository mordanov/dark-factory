"""FastAPI dependencies for authentication and service injection."""

from __future__ import annotations

import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth_adapter import AuthAdapter
from src.core.config import get_settings
from src.core.exceptions import ForbiddenError, UnauthorizedError
from src.db.session import get_db
from src.models.models import User
from src.repositories.user_repo import UserRepository
from src.services.session_service import SessionService
from src.services.ticket_manager.client import TicketManagerClient, get_ticket_manager_client

_bearer = HTTPBearer(auto_error=False)
_adapter = AuthAdapter(get_settings())


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        claims = await _adapter.verify(credentials.credentials)
    except (JWTError, UnauthorizedError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        ) from exc
    except NotImplementedError as exc:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Keycloak auth not configured"
        ) from exc
    user = await UserRepository(db).get_by_id(uuid.UUID(claims["sub"]))
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is disabled")
    return user


async def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user


def get_session_service(
    db: AsyncSession = Depends(get_db),
    tm: TicketManagerClient = Depends(get_ticket_manager_client),
) -> SessionService:
    return SessionService(db, tm)
