"""FastAPI dependency injection."""
from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from motor.motor_asyncio import AsyncIOMotorDatabase
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import verify_access_token
from src.db.mongo import get_mongo_db
from src.db.postgres import get_db
from src.services.document_store.store import DocumentStore
from src.services.tm_client.client import TicketManagerClient, get_tm_client

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict:
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        return verify_access_token(credentials.credentials)
    except JWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc


async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin required")
    return user


def get_doc_store(mongo: AsyncIOMotorDatabase = Depends(get_mongo_db)) -> DocumentStore:
    return DocumentStore(mongo)


def get_tm(tm: TicketManagerClient = Depends(get_tm_client)) -> TicketManagerClient:
    return tm
