"""Shared pytest fixtures and configuration."""

import os
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from jose import jwt
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.core.database import get_db
from src.main import app

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/ticket_manager_test",
)
_TEST_JWT_SECRET = "test-secret-do-not-use-in-production"


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        await session.rollback()
    await engine.dispose()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession):
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
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
