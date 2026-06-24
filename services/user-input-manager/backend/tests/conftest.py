"""Shared pytest fixtures and configuration."""

import asyncio
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from jose import jwt
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from src.db.session import Base, get_db
from src.main import create_app

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
_TEST_JWT_SECRET = "test-secret-do-not-use-in-production"


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


# ---------------------------------------------------------------------------
# Planning-agent fixtures
# ---------------------------------------------------------------------------

VALID_PLAN_DICT = {
    "epic": {
        "local_id": "epic-1",
        "title": "Build user auth",
        "description": "Implement authentication system",
        "ticket_type": "epic",
    },
    "stories": [
        {
            "local_id": "story-1",
            "title": "Backend auth",
            "description": "Implement JWT auth on the backend",
            "ticket_type": "story",
            "tasks": [
                {
                    "local_id": "task-1-1",
                    "title": "Create JWT service",
                    "description": "Implement token generation and validation",
                    "ticket_type": "task",
                    "complexity": "M",
                    "depends_on": [],
                },
                {
                    "local_id": "task-1-2",
                    "title": "Create auth endpoints",
                    "description": "Add /login and /refresh endpoints",
                    "ticket_type": "task",
                    "complexity": "M",
                    "depends_on": ["task-1-1"],
                },
            ],
        }
    ],
}


@pytest_asyncio.fixture
async def approved_session(db):
    from src.models.models import PromptSession

    session = PromptSession(
        user_id="user-sub-001",
        session_type="new_project",
        tm_project_name="Test Project",
        tm_project_id="proj-test",
        status="approved",
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


@pytest_asyncio.fixture
async def prompt_plan(db):
    from src.models.models import PromptPlan, PromptSession

    session = PromptSession(
        user_id="user-sub-001",
        session_type="new_project",
        tm_project_name="Test Project",
        tm_project_id="proj-test",
        status="approved",
    )
    db.add(session)
    await db.flush()

    plan = PromptPlan(
        session_id=session.id,
        status="ready",
        plan_content=VALID_PLAN_DICT,
    )
    db.add(plan)
    await db.commit()
    await db.refresh(plan)
    return plan


@pytest.fixture
def mock_tm_plan_client():
    client = MagicMock()
    client.create_epic = AsyncMock(return_value="tm-epic-1")
    client.create_story = AsyncMock(return_value="tm-story-1")
    client.create_task = AsyncMock(return_value="tm-task-1")
    return client


@pytest.fixture
def mock_httpx_post_success():
    response = MagicMock()
    response.status_code = 201
    response.json.return_value = {"project_id": "proj-1", "stored_at": "2026-01-01T00:00:00"}
    return response
