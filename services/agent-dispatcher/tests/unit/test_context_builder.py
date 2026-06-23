"""Unit tests for context_builder."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from src.schemas.schemas import AgentContext


@pytest.fixture
def sample_ticket():
    return MagicMock(
        id="TKT-001",
        project_id="proj-123",
        assigned_agent="backend",
        title="Implement login",
        ticket_type="feature",
        description="Build a login endpoint",
        fsm_status="implementation",
    )


@pytest.fixture
def sample_context():
    return AgentContext(
        ticket_id="TKT-001",
        project_id="proj-123",
        agent_id="backend",
        ticket_title="Implement login",
        ticket_type="feature",
        description="Build a login endpoint",
    )


async def test_all_sections_present_when_services_respond(sample_ticket, tmp_path):
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "backend.md").write_text("You are the backend developer.")

    with (
        patch("src.services.context_builder.get_settings") as mock_settings,
        patch("src.services.context_builder.httpx.AsyncClient") as mock_client_cls,
        patch("src.services.context_builder.create_service_token", return_value="jwt-token"),
    ):
        settings = MagicMock()
        settings.agent_prompts_dir = str(prompts_dir)
        settings.context_distiller_base_url = "http://mock-distiller"
        settings.ticket_manager_base_url = "http://mock-tm"
        settings.context_max_tokens = 4000
        settings.agent_runner_mode = "claude_code"
        mock_settings.return_value = settings

        mock_resp = AsyncMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"content": "project memory text"}
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value = mock_client

        from src.services.context_builder import build_context

        context_str, _ = await build_context(sample_ticket, "backend", None)

    assert "## Your Role" in context_str
    assert "## Ticket" in context_str
    assert "## Description" in context_str
    assert "## Task Manager Access" in context_str
    assert "## Completion and Metrics Reporting" in context_str
    assert "report-task-metrics.sh" in context_str
    assert "task-metrics" in context_str


async def test_missing_project_memory_empty_section(sample_ticket, tmp_path):
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "backend.md").write_text("You are backend.")

    with (
        patch("src.services.context_builder.get_settings") as mock_settings,
        patch("src.services.context_builder.httpx.AsyncClient") as mock_client_cls,
        patch("src.services.context_builder.create_service_token", return_value="jwt"),
    ):
        settings = MagicMock()
        settings.agent_prompts_dir = str(prompts_dir)
        settings.context_distiller_base_url = "http://mock-distiller"
        settings.ticket_manager_base_url = "http://mock-tm"
        settings.context_max_tokens = 4000
        settings.agent_runner_mode = "claude_code"
        mock_settings.return_value = settings

        mock_resp = AsyncMock()
        mock_resp.status_code = 404
        mock_resp.raise_for_status.side_effect = Exception("404")
        mock_resp.json.return_value = {}

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(side_effect=Exception("unreachable"))
        mock_client_cls.return_value = mock_client

        from src.services.context_builder import build_context

        context_str, _ = await build_context(sample_ticket, "backend", None)

    assert "## Project Context" in context_str


async def test_service_jwt_absent_from_context_snapshot(sample_ticket, tmp_path):
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "backend.md").write_text("role text")

    with (
        patch("src.services.context_builder.get_settings") as mock_settings,
        patch("src.services.context_builder.httpx.AsyncClient") as mock_client_cls,
        patch("src.services.context_builder.create_service_token", return_value="SECRET_JWT"),
    ):
        settings = MagicMock()
        settings.agent_prompts_dir = str(prompts_dir)
        settings.context_distiller_base_url = "http://mock-distiller"
        settings.ticket_manager_base_url = "http://mock-tm"
        settings.context_max_tokens = 4000
        settings.agent_runner_mode = "claude_code"
        mock_settings.return_value = settings

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(side_effect=Exception("unreachable"))
        mock_client_cls.return_value = mock_client

        from src.services.context_builder import build_context, build_context_snapshot

        context_str, jwt_value = await build_context(sample_ticket, "backend", None)
        snapshot = build_context_snapshot(sample_ticket, "backend")

    assert "SECRET_JWT" in context_str
    assert jwt_value == "SECRET_JWT"
    assert "SECRET_JWT" not in str(snapshot)


async def test_context_max_tokens_truncation(sample_ticket, tmp_path):
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "backend.md").write_text("role")

    with (
        patch("src.services.context_builder.get_settings") as mock_settings,
        patch("src.services.context_builder.httpx.AsyncClient") as mock_client_cls,
        patch("src.services.context_builder.create_service_token", return_value="jwt"),
    ):
        settings = MagicMock()
        settings.agent_prompts_dir = str(prompts_dir)
        settings.context_distiller_base_url = "http://mock-distiller"
        settings.ticket_manager_base_url = "http://mock-tm"
        settings.context_max_tokens = 10
        settings.agent_runner_mode = "claude_code"
        mock_settings.return_value = settings

        long_memory = " ".join(["word"] * 500)
        mock_resp = AsyncMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"content": long_memory}

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value = mock_client

        from src.services.context_builder import build_context

        context_str, _ = await build_context(sample_ticket, "backend", None)

    word_count = len(context_str.split())
    assert word_count < 500 + 100


async def test_completion_metrics_section_present(sample_ticket, tmp_path):
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "backend.md").write_text("role")

    with (
        patch("src.services.context_builder.get_settings") as mock_settings,
        patch("src.services.context_builder.httpx.AsyncClient") as mock_client_cls,
        patch("src.services.context_builder.create_service_token", return_value="jwt"),
    ):
        settings = MagicMock()
        settings.agent_prompts_dir = str(prompts_dir)
        settings.context_distiller_base_url = "http://mock-distiller"
        settings.ticket_manager_base_url = "http://mock-tm"
        settings.context_max_tokens = 4000
        settings.agent_runner_mode = "claude_code"
        mock_settings.return_value = settings

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(side_effect=Exception("unreachable"))
        mock_client_cls.return_value = mock_client

        from src.services.context_builder import build_context

        context_str, _ = await build_context(sample_ticket, "backend", None)

    assert "## Completion and Metrics Reporting" in context_str
    assert "report-task-metrics.sh" in context_str
    assert "task-metrics" in context_str
    assert "[RESULT]" in context_str
