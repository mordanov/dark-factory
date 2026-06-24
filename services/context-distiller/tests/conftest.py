"""Shared test fixtures."""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from jose import jwt
from mongomock_motor import AsyncMongoMockClient
from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from src.db.postgres import Base
from src.models import Job

_TEST_JWT_SECRET = "test-secret-do-not-use-in-production"


# SQLite doesn't support JSONB — swap it out for tests only
def _patch_jsonb_for_sqlite():
    from sqlalchemy import event

    @event.listens_for(Base.metadata, "before_create")
    def before_create(target, connection, **kw):
        pass

    for table in Base.metadata.tables.values():
        for col in table.columns:
            if isinstance(col.type, JSONB):
                col.type = JSON()


# ---------------------------------------------------------------------------
# PostgreSQL — in-memory SQLite for tests
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    _patch_jsonb_for_sqlite()
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


# ---------------------------------------------------------------------------
# MongoDB — mongomock-motor in-process
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def mongo_db():
    client = AsyncMongoMockClient()
    return client["test_dark_factory_docs"]


# ---------------------------------------------------------------------------
# FastAPI test app
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def test_client(db_session, mongo_db) -> AsyncGenerator[AsyncClient, None]:
    from src.api.dependencies import get_current_user
    from src.db.mongo import get_mongo_db
    from src.db.postgres import get_db
    from src.main import app

    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_mongo_db] = lambda: mongo_db
    app.dependency_overrides[get_current_user] = lambda: {"sub": "test-user"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Auth fixtures (Keycloak-shaped HS256 tokens for AUTH_MODE=local)
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def set_auth_mode(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "local")
    monkeypatch.setenv("TEST_JWT_SECRET", _TEST_JWT_SECRET)
    from src.core import config as cfg

    cfg.get_settings.cache_clear()
    yield
    cfg.get_settings.cache_clear()


def _make_token(sub: str, email: str, roles: list[str]) -> str:
    payload = {
        "sub": sub,
        "email": email,
        "preferred_username": email,
        "realm_access": {"roles": roles},
        "exp": datetime.now(UTC) + timedelta(hours=1),
    }
    return jwt.encode(payload, _TEST_JWT_SECRET, algorithm="HS256")


@pytest.fixture
def user_token() -> str:
    return _make_token("user-sub-001", "user@test.local", ["user"])


@pytest.fixture
def admin_token() -> str:
    return _make_token("admin-sub-001", "admin@test.local", ["user", "administrator"])


@pytest.fixture
def auth_headers(user_token) -> dict:
    return {"Authorization": f"Bearer {user_token}"}


@pytest.fixture
def admin_headers(admin_token) -> dict:
    return {"Authorization": f"Bearer {admin_token}"}


# ---------------------------------------------------------------------------
# Sample fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_job_payload() -> dict:
    return {
        "ticket_id": "TICKET-001",
        "project_id": "proj-1",
        "audit_trail": [
            {
                "action": "ADVANCE",
                "from_state": "testing",
                "to_state": "done",
                "details": "Tests passed",
                "created_at": "2026-06-20T10:00:00Z",
            }
        ],
        "ticket_snapshot": {
            "title": "Add auth",
            "description": "JWT auth for all endpoints",
            "ticket_type": "feature",
            "tags": ["auth"],
            "fsm_status": "done",
        },
    }


@pytest.fixture
def valid_memory_yaml() -> str:
    return """\
project_id: proj-1
last_updated: "2026-06-20T10:00:00Z"
last_ticket_id: TICKET-001
architecture:
  - "JWT middleware added"
recent_changes:
  - ticket_id: TICKET-001
    summary: "Added JWT auth"
    files_changed: ["src/auth.py"]
    risks: []
open_risks: []
known_constraints:
  - "All endpoints must be async"
tech_stack:
  backend: "Python 3.12, FastAPI"
  frontend: "N/A"
  database: "PostgreSQL"
  infra: "Docker Compose"
"""
