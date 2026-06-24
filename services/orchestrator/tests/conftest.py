"""Shared test fixtures."""

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
from src.db.postgres import Base, get_db
from src.main import create_app
from src.schemas.schemas import TmTicket

TEST_PG_URL = "sqlite+aiosqlite:///:memory:"
_TEST_JWT_SECRET = "test-secret-do-not-use-in-production"


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def engine_fixture():
    engine = create_async_engine(
        TEST_PG_URL, connect_args={"check_same_thread": False}, poolclass=StaticPool
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
def mock_tm():
    tm = MagicMock()
    tm.get_pending_tickets = AsyncMock(
        return_value=[
            {
                "id": "t-1",
                "project_id": "p-1",
                "title": "Test ticket",
                "description": "## Acceptance Criteria\n- [ ] works",
                "ticket_type": "feature",
                "tags": [],
                "fsm_status": "backlog",
                "blocked_reason": None,
                "brainstorm_round": 0,
                "assigned_agent": None,
                "override": False,
                "override_reason": None,
                "dependencies": [],
                "subtasks": [],
                "created_at": None,
                "updated_at": None,
            }
        ]
    )
    tm.get_ticket_full = AsyncMock(
        return_value={
            "id": "t-1",
            "project_id": "p-1",
            "title": "Test ticket",
            "description": "## Acceptance Criteria\n- [ ] works",
            "ticket_type": "feature",
            "tags": [],
            "fsm_status": "triage",
            "blocked_reason": None,
            "brainstorm_round": 0,
            "assigned_agent": None,
            "override": False,
            "override_reason": None,
            "dependencies": [],
            "subtasks": [],
            "created_at": None,
            "updated_at": None,
        }
    )
    tm.update_fsm = AsyncMock(return_value={})
    tm.get_fsm_status_batch = AsyncMock(return_value={})
    tm.manage_tags = AsyncMock(return_value={"tags": []})
    return tm


@pytest.fixture
def mock_doc_store():
    store = MagicMock()
    store.get_memory = AsyncMock(return_value=None)
    store.list_adrs = AsyncMock(return_value=[])
    store.save_memory = AsyncMock()
    store.save_adr = AsyncMock(return_value="ADR-001")
    return store


@pytest.fixture
def sample_ticket():
    return TmTicket(
        id="t-1",
        project_id="p-1",
        title="Add login",
        description="## Acceptance Criteria\n- [ ] JWT login works",
        ticket_type="feature",
        tags=[],
        fsm_status="triage",
        brainstorm_round=0,
        dependencies=[],
    )
