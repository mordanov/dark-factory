"""FastAPI dependency injection."""

from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from motor.motor_asyncio import AsyncIOMotorDatabase
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth_adapter import AuthAdapter
from src.core.config import get_settings
from src.db.mongo import get_mongo_db
from src.db.postgres import get_db
from src.services.document_store.store import DocumentStore
from src.services.tm_client.client import TicketManagerClient, get_tm_client

_bearer = HTTPBearer(auto_error=False)
_adapter = AuthAdapter(get_settings())


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict:
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        return await _adapter.verify(credentials.credentials)
    except JWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail="Keycloak auth not configured") from exc


async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin required")
    return user


def get_doc_store(mongo: AsyncIOMotorDatabase = Depends(get_mongo_db)) -> DocumentStore:
    return DocumentStore(mongo)


def get_tm(tm: TicketManagerClient = Depends(get_tm_client)) -> TicketManagerClient:
    return tm
