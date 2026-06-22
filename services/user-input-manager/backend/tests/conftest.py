"""Shared pytest fixtures and configuration."""

import asyncio
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from src.core.security import create_access_token, hash_password
from src.db.session import Base, get_db
from src.main import create_app
from src.models.models import User

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def engine_fixture():
    engine = create_async_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db(engine_fixture) -> AsyncGenerator[AsyncSession, None]:
    factory = async_sessionmaker(engine_fixture, expire_on_commit=False)
    async with factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def app(db):
    application = create_app()
    application.dependency_overrides[get_db] = lambda: db
    return application


@pytest_asyncio.fixture
async def client(app) -> AsyncGenerator[AsyncClient, None]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


# ---------------------------------------------------------------------------
# User factories
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def admin_user(db) -> User:
    user = User(
        email="admin@test.com",
        password_hash=hash_password("Admin1234!"),
        full_name="Test Admin",
        is_admin=True,
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest_asyncio.fixture
async def regular_user(db) -> User:
    user = User(
        email="user@test.com",
        password_hash=hash_password("User1234!"),
        full_name="Test User",
        is_admin=False,
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest.fixture
def admin_token(admin_user) -> str:
    return create_access_token(str(admin_user.id), is_admin=True)


@pytest.fixture
def user_token(regular_user) -> str:
    return create_access_token(str(regular_user.id), is_admin=False)


@pytest.fixture
def auth_headers(user_token) -> dict:
    return {"Authorization": f"Bearer {user_token}"}


@pytest.fixture
def admin_headers(admin_token) -> dict:
    return {"Authorization": f"Bearer {admin_token}"}


# ---------------------------------------------------------------------------
# Mock external services
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_tm_client():
    client = MagicMock()
    client.list_projects = AsyncMock(
        return_value=[
            {"id": "proj-1", "name": "Alpha Project", "description": "desc"},
        ]
    )
    client.get_project = AsyncMock(return_value={"id": "proj-1", "name": "Alpha Project"})
    client.create_project = AsyncMock(return_value={"id": "new-proj", "name": "New Project"})
    client.list_tickets = AsyncMock(
        return_value=[
            {"id": "t-1", "title": "Existing ticket", "status": "open", "type": "feature"},
        ]
    )
    client.build_project_context = AsyncMock(
        return_value="Existing tickets:\n- [t-1] Existing ticket"
    )
    client.create_ticket = AsyncMock(return_value={"id": "new-ticket-id", "title": "Test Ticket"})
    return client


@pytest.fixture
def mock_llm_result():
    from src.services.llm.openai_service import RefinementResult

    return RefinementResult(
        refined_prompt="Refined prompt text with all details.",
        assessment="The prompt is clear and detailed.",
        questions="",
        suggested_title="Add user authentication feature",
        is_ready=True,
    )
