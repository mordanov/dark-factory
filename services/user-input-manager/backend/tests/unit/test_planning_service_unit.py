"""Unit tests for PlanningService covering lightweight branches not in integration tests."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from src.core.exceptions import ForbiddenError, NotFoundError
from src.schemas.schemas import AgentConfig, AgentOverride
from src.services.planning_service import PlanningService


def _make_svc():
    db = MagicMock()
    tm = MagicMock()
    svc = PlanningService.__new__(PlanningService)
    svc._plan_repo = MagicMock()
    svc._session_repo = MagicMock()
    svc._tm = tm
    return svc


# ---------------------------------------------------------------------------
# _get_session_for_user — error branches
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_session_raises_not_found_when_session_missing():
    svc = _make_svc()
    svc._session_repo.get_by_id = AsyncMock(return_value=None)

    with pytest.raises(NotFoundError):
        await svc._get_session_for_user(uuid.uuid4(), uuid.uuid4())


@pytest.mark.asyncio
async def test_get_session_raises_forbidden_for_wrong_user():
    svc = _make_svc()
    session = MagicMock()
    session.user_id = uuid.uuid4()
    svc._session_repo.get_by_id = AsyncMock(return_value=session)

    with pytest.raises(ForbiddenError):
        await svc._get_session_for_user(uuid.uuid4(), uuid.uuid4())  # different user_id


# ---------------------------------------------------------------------------
# get_plan — not found branch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_plan_raises_not_found_when_plan_missing():
    svc = _make_svc()
    user_id = uuid.uuid4()
    session = MagicMock()
    session.user_id = user_id
    svc._session_repo.get_by_id = AsyncMock(return_value=session)
    svc._plan_repo.get_by_session_id = AsyncMock(return_value=None)

    with pytest.raises(NotFoundError):
        await svc.get_plan(uuid.uuid4(), user_id)


# ---------------------------------------------------------------------------
# _store_agent_config — best-effort HTTP success and failure paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_store_agent_config_posts_to_context_distiller():
    svc = _make_svc()
    agent_config = AgentConfig(
        project_id="proj-1",
        tech_stack=["Python"],
        agent_overrides=[AgentOverride(agent_id="backend", override_text="Use async")],
    )

    mock_response = MagicMock()
    mock_response.status_code = 201

    with patch("src.services.planning_service.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        await svc._store_agent_config("proj-1", agent_config)

    mock_client.post.assert_awaited_once()
    call_args = mock_client.post.call_args
    assert "proj-1" in call_args[0][0]
    assert call_args[1]["json"]["project_id"] == "proj-1"


@pytest.mark.asyncio
async def test_store_agent_config_never_raises_on_http_error():
    svc = _make_svc()
    agent_config = AgentConfig(project_id="proj-1", tech_stack=[], agent_overrides=[])

    with patch(
        "src.services.planning_service.httpx.AsyncClient",
        side_effect=Exception("connection refused"),
    ):
        await svc._store_agent_config("proj-1", agent_config)  # must not raise


@pytest.mark.asyncio
async def test_store_agent_config_logs_non_2xx_response():
    svc = _make_svc()
    agent_config = AgentConfig(project_id="proj-1", tech_stack=[], agent_overrides=[])

    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.text = "Internal Server Error"

    with patch("src.services.planning_service.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        await svc._store_agent_config("proj-1", agent_config)  # must not raise


# ---------------------------------------------------------------------------
# _create_tickets — plan not found path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_tickets_returns_early_when_plan_missing():
    svc = _make_svc()
    svc._plan_repo.get_by_session_id = AsyncMock(return_value=None)

    await svc._create_tickets(uuid.uuid4())  # should not raise

    svc._tm.create_epic.assert_not_called()


@pytest.mark.asyncio
async def test_create_tickets_returns_early_when_session_project_id_missing():
    svc = _make_svc()
    plan = MagicMock()
    plan.plan_content = {"epic": {}, "stories": []}
    svc._plan_repo.get_by_session_id = AsyncMock(return_value=plan)

    session = MagicMock()
    session.tm_project_id = None
    svc._session_repo.get_by_id = AsyncMock(return_value=session)

    await svc._create_tickets(uuid.uuid4())  # should not raise

    svc._tm.create_epic.assert_not_called()
