"""FastAPI dependencies for authentication and service injection."""

from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth_adapter import KeycloakValidator, UnauthorizedError, UserClaims
from src.db.session import get_db
from src.services.session_service import SessionService
from src.services.ticket_manager.client import TicketManagerClient, get_ticket_manager_client

_bearer = HTTPBearer(auto_error=False)
_validator = KeycloakValidator()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> UserClaims:
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        return await _validator.verify(credentials.credentials)
    except UnauthorizedError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc


async def require_admin(claims: UserClaims = Depends(get_current_user)) -> UserClaims:
    if not claims.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Administrator role required"
        )
    return claims


def get_session_service(
    db: AsyncSession = Depends(get_db),
    tm: TicketManagerClient = Depends(get_ticket_manager_client),
) -> SessionService:
    return SessionService(db, tm)
