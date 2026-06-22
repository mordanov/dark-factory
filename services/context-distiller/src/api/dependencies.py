"""FastAPI dependency injectors."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from motor.motor_asyncio import AsyncIOMotorDatabase
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth_adapter import AuthAdapter
from src.core.config import get_settings
from src.db.mongo import get_mongo_db
from src.db.postgres import get_db

_bearer = HTTPBearer(auto_error=False)
_adapter = AuthAdapter(get_settings())


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict:
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        return await _adapter.verify(credentials.credentials)
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except NotImplementedError as exc:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Keycloak auth not configured",
        ) from exc


DbDep = Annotated[AsyncSession, Depends(get_db)]
MongoDep = Annotated[AsyncIOMotorDatabase, Depends(get_mongo_db)]
UserDep = Annotated[dict, Depends(get_current_user)]
