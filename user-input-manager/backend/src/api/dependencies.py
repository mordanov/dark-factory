"""FastAPI dependencies for authentication and service injection."""
from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ForbiddenError, UnauthorizedError
from src.db.session import get_db
from src.models.models import User
from src.services.auth_service import AuthService
from src.services.session_service import SessionService
from src.services.ticket_manager.client import TicketManagerClient, get_ticket_manager_client

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        return await AuthService(db).get_current_user(credentials.credentials)
    except (UnauthorizedError, ForbiddenError) as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail)


async def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user


def get_session_service(
    db: AsyncSession = Depends(get_db),
    tm: TicketManagerClient = Depends(get_ticket_manager_client),
) -> SessionService:
    return SessionService(db, tm)
