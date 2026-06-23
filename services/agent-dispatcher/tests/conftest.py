"""Shared pytest fixtures for Agent Dispatcher tests."""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from src.core.config import Settings
from src.db.session import Base
from src.main import create_app

TEST_DATABASE_URL = "postgresql+asyncpg://aleksandr@localhost/df_dispatcher_test"


@pytest.fixture
def mock_settings() -> Settings:
    return Settings(
        database_url=TEST_DATABASE_URL,
        jwt_secret_key="test-secret-key",
        auth_mode="local",
        agent_runner_mode="claude_code",
        poll_interval_seconds=1,
        worker_max_concurrent_runs=2,
        orchestrator_base_url="http://mock-orchestrator",
        ticket_manager_base_url="http://mock-tm",
        context_distiller_base_url="http://mock-distiller",
    )


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
async def async_client(mock_settings) -> AsyncGenerator[AsyncClient, None]:
    app = create_app()
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client
