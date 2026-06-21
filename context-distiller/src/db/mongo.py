"""Motor async MongoDB client."""
from __future__ import annotations
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from src.core.config import get_settings

_client: AsyncIOMotorClient | None = None


def get_mongo_client() -> AsyncIOMotorClient:
    global _client
    if _client is None:
        settings = get_settings()
        _client = AsyncIOMotorClient(settings.mongo_url)
    return _client


def get_mongo_db() -> AsyncIOMotorDatabase:
    settings = get_settings()
    return get_mongo_client()[settings.mongo_db_name]
