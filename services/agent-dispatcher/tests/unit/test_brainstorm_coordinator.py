"""Unit tests for BrainstormCoordinator."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
from src.schemas.schemas import AgentResult


def make_ticket(ticket_id="TKT-BS-TEST", project_id="proj-1"):
    return MagicMock(
        id=ticket_id,
        project_id=project_id,
        assigned_agent="software_architect",
        fsm_status="architecture_review",
        ticket_type="feature",
        title="Review design",
        description="Desc",
    )


def make_result_stdout(status="completed", consensus=None, tm_comment="comment"):
    data = {
        "status": status,
        "summary": "Summary",
        "tm_comment": tm_comment,
        "brainstorm_consensus": consensus,
        "errors": [],
        "artifacts": [],
    }
    return f"[RESULT]\n{json.dumps(data)}\n[/RESULT]"


async def test_two_agents_run_sequentially(db_session, tmp_path):
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "software_architect.md").write_text("SA role")
    (prompts_dir / "security_architect.md").write_text("SEC role")

    ticket = make_ticket()
    run_order: list[str] = []

    async def mock_run(agent_id, system_prompt, context, timeout):
        run_order.append(agent_id)
        return (0, make_result_stdout())

    mock_runner = AsyncMock()
    mock_runner.run.side_effect = mock_run

    with (
        patch("src.services.brainstorm_coordinator.get_settings") as mock_settings,
        patch(
            "src.services.brainstorm_coordinator.build_context",
            return_value=("context", "jwt-token"),
        ),
        patch("src.services.brainstorm_coordinator.build_context_snapshot", return_value={}),
    ):
        settings = MagicMock()
        settings.agent_prompts_dir = str(prompts_dir)
        settings.agent_runner_mode = "claude_code"
        settings.brainstorm_agents_list = ["software_architect", "security_architect"]
        settings.brainstorm_max_rounds = 2
        settings.agent_timeout_for = MagicMock(return_value=300)
        mock_settings.return_value = settings

        from src.services.brainstorm_coordinator import BrainstormCoordinator

        coordinator = BrainstormCoordinator(mock_runner)
        result = await coordinator.run_brainstorm(ticket, db_session)

    assert run_order[0] == "software_architect"
    assert run_order[1] == "security_architect"


async def test_early_exit_on_first_agent_agreed(db_session, tmp_path):
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "software_architect.md").write_text("SA role")
    (prompts_dir / "security_architect.md").write_text("SEC role")

    ticket = make_ticket()
    call_count = 0

    async def mock_run(agent_id, system_prompt, context, timeout):
        nonlocal call_count
        call_count += 1
        return (0, make_result_stdout(consensus="agreed"))

    mock_runner = AsyncMock()
    mock_runner.run.side_effect = mock_run

    with (
        patch("src.services.brainstorm_coordinator.get_settings") as mock_settings,
        patch(
            "src.services.brainstorm_coordinator.build_context", return_value=("ctx", "jwt-token")
        ),
        patch("src.services.brainstorm_coordinator.build_context_snapshot", return_value={}),
    ):
        settings = MagicMock()
        settings.agent_prompts_dir = str(prompts_dir)
        settings.agent_runner_mode = "claude_code"
        settings.brainstorm_agents_list = ["software_architect", "security_architect"]
        settings.brainstorm_max_rounds = 3
        settings.agent_timeout_for = MagicMock(return_value=300)
        mock_settings.return_value = settings

        from src.services.brainstorm_coordinator import BrainstormCoordinator

        coordinator = BrainstormCoordinator(mock_runner)
        data = await coordinator.run_brainstorm(ticket, db_session)

    assert call_count == 1
    assert data["consensus"] == "agreed"
    assert data["concluded"] is True


async def test_max_rounds_enforced(db_session, tmp_path):
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "software_architect.md").write_text("SA role")
    (prompts_dir / "security_architect.md").write_text("SEC role")

    ticket = make_ticket()
    call_count = 0

    async def mock_run(agent_id, system_prompt, context, timeout):
        nonlocal call_count
        call_count += 1
        return (0, make_result_stdout(consensus=None))

    mock_runner = AsyncMock()
    mock_runner.run.side_effect = mock_run

    with (
        patch("src.services.brainstorm_coordinator.get_settings") as mock_settings,
        patch(
            "src.services.brainstorm_coordinator.build_context", return_value=("ctx", "jwt-token")
        ),
        patch("src.services.brainstorm_coordinator.build_context_snapshot", return_value={}),
    ):
        settings = MagicMock()
        settings.agent_prompts_dir = str(prompts_dir)
        settings.agent_runner_mode = "claude_code"
        settings.brainstorm_agents_list = ["software_architect", "security_architect"]
        settings.brainstorm_max_rounds = 2
        settings.agent_timeout_for = MagicMock(return_value=300)
        mock_settings.return_value = settings

        from src.services.brainstorm_coordinator import BrainstormCoordinator

        coordinator = BrainstormCoordinator(mock_runner)
        data = await coordinator.run_brainstorm(ticket, db_session)

    assert call_count == 2 * 2
    assert data["rounds_completed"] == 2
    assert data["consensus"] is None


async def test_api_mode_injects_previous_responses(db_session, tmp_path):
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "software_architect.md").write_text("SA role")
    (prompts_dir / "security_architect.md").write_text("SEC role")

    ticket = make_ticket()
    captured_prev_responses: list = []

    async def mock_run(agent_id, system_prompt, context, timeout):
        return (0, make_result_stdout(tm_comment=f"Response from {agent_id}"))

    mock_runner = AsyncMock()
    mock_runner.run.side_effect = mock_run

    async def mock_build_context(ticket, agent_id, session, previous_responses=None):
        captured_prev_responses.append((agent_id, previous_responses))
        return (f"context for {agent_id}", "jwt-token")

    with (
        patch("src.services.brainstorm_coordinator.get_settings") as mock_settings,
        patch("src.services.brainstorm_coordinator.build_context", side_effect=mock_build_context),
        patch("src.services.brainstorm_coordinator.build_context_snapshot", return_value={}),
    ):
        settings = MagicMock()
        settings.agent_prompts_dir = str(prompts_dir)
        settings.agent_runner_mode = "api"
        settings.brainstorm_agents_list = ["software_architect", "security_architect"]
        settings.brainstorm_max_rounds = 1
        settings.agent_timeout_for = MagicMock(return_value=300)
        mock_settings.return_value = settings

        from src.services.brainstorm_coordinator import BrainstormCoordinator

        coordinator = BrainstormCoordinator(mock_runner)
        await coordinator.run_brainstorm(ticket, db_session)

    sa_call = next(c for c in captured_prev_responses if c[0] == "software_architect")
    sec_call = next(c for c in captured_prev_responses if c[0] == "security_architect")
    assert sa_call[1] is None
    assert sec_call[1] is not None
    assert "software_architect" in sec_call[1]
