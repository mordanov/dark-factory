"""Shared pytest fixtures and configuration."""

import asyncio
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
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
    result = await db.execute(select(User).where(User.email == "admin@test.com"))
    existing = result.scalar_one_or_none()
    if existing:
        return existing
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
    result = await db.execute(select(User).where(User.email == "user@test.com"))
    existing = result.scalar_one_or_none()
    if existing:
        return existing
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
async def approved_session(db, regular_user):
    from src.models.models import PromptSession

    session = PromptSession(
        user_id=regular_user.id,
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
async def prompt_plan(db, regular_user):
    from src.models.models import PromptPlan, PromptSession

    session = PromptSession(
        user_id=regular_user.id,
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
