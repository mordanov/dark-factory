"""Shared pytest fixtures for Agent Dispatcher tests."""

from __future__ import annotations

import os as _os
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from jose import jwt
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from src.core.config import Settings
from src.db.session import Base
from src.main import create_app

TEST_DATABASE_URL = _os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://aleksandr@localhost/df_dispatcher_test",
)
_TEST_JWT_SECRET = "test-secret-do-not-use-in-production"


@pytest.fixture
def mock_settings() -> Settings:
    return Settings(
        database_url=TEST_DATABASE_URL,
        test_jwt_secret=_TEST_JWT_SECRET,
        auth_mode="local",
        agent_runner_mode="claude_code",
        poll_interval_seconds=1,
        worker_max_concurrent_runs=2,
        orchestrator_base_url="http://mock-orchestrator",
        ticket_manager_base_url="http://mock-tm",
        context_distiller_base_url="http://mock-distiller",
    )


def _make_engine(url: str):
    """Create an async engine; strip pool args unsupported by SQLite."""
    if url.startswith("sqlite"):
        import sqlite3
        import uuid as _uuid_mod

        from sqlalchemy.pool import StaticPool

        # SQLite doesn't know uuid.UUID — serialize to string at the adapter level
        sqlite3.register_adapter(_uuid_mod.UUID, str)
        sqlite3.register_converter("UUID", lambda b: _uuid_mod.UUID(b.decode()))

        return create_async_engine(
            url,
            echo=False,
            connect_args={"check_same_thread": False, "detect_types": sqlite3.PARSE_DECLTYPES},
            poolclass=StaticPool,
        )
    return create_async_engine(url, echo=False)


def _create_all_compat(conn):
    """create_all with PostgreSQL-type fallbacks for SQLite."""
    from sqlalchemy import JSON, String
    from sqlalchemy.dialects.postgresql import ARRAY as PG_ARRAY
    from sqlalchemy.dialects.postgresql import JSONB, UUID

    is_sqlite = conn.dialect.name == "sqlite"
    if not is_sqlite:
        Base.metadata.create_all(conn)
        return

    # Swap out PostgreSQL-only types so SQLite can create the schema
    from sqlalchemy import ARRAY as SA_ARRAY
    from sqlalchemy import event

    def _before_create(target, connection, **kw):
        for table in target.tables.values():
            for col in table.columns:
                if isinstance(col.type, JSONB):
                    col.type = JSON()
                elif isinstance(col.type, UUID):
                    col.type = String(36)
                elif isinstance(col.type, (PG_ARRAY, SA_ARRAY)):
                    col.type = JSON()

    event.listen(Base.metadata, "before_create", _before_create)
    try:
        Base.metadata.create_all(conn)
    finally:
        event.remove(Base.metadata, "before_create", _before_create)


def _drop_all_compat(conn):
    Base.metadata.drop_all(conn)


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    engine = _make_engine(TEST_DATABASE_URL)
    async with engine.begin() as conn:
        await conn.run_sync(_create_all_compat)

    factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(_drop_all_compat)
    await engine.dispose()


@pytest.fixture
async def async_client(mock_settings) -> AsyncGenerator[AsyncClient, None]:
    app = create_app()
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client


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
