"""FastAPI dependency injectors."""
from __future__ import annotations
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from motor.motor_asyncio import AsyncIOMotorDatabase
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import decode_token
from src.db.mongo import get_mongo_db
from src.db.postgres import get_db

_bearer = HTTPBearer()


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)],
) -> dict:
    return decode_token(credentials.credentials)


DbDep = Annotated[AsyncSession, Depends(get_db)]
MongoDep = Annotated[AsyncIOMotorDatabase, Depends(get_mongo_db)]
UserDep = Annotated[dict, Depends(get_current_user)]
