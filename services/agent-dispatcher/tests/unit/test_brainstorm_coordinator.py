"""Unit tests for BrainstormCoordinator."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from src.schemas.schemas import AgentResult
from src.services.brainstorm.cli_reader import BrainstormMessage, BrainstormTranscript


def make_ticket(ticket_id="TKT-BS-TEST", project_id="proj-1"):
    return MagicMock(
        id=ticket_id,
        project_id=project_id,
        assigned_agent="software-architect",
        fsm_status="architecture_review",
        ticket_type="feature",
        title="Review design",
        description="Desc",
    )


def make_registry(project_name: str = "df-TKT-BS-TEST") -> MagicMock:
    registry = MagicMock()
    registry.brainstorm_project_name.return_value = project_name
    return registry


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


def make_mock_cli_reader(messages=None):
    """Return a mock BrainstormCLIReader that returns given messages."""
    reader = MagicMock()
    reader.read = AsyncMock(return_value=messages or [])
    return reader


# ---------------------------------------------------------------------------
# Existing tests — updated to pass mock registry
# ---------------------------------------------------------------------------


async def test_two_agents_run_sequentially(db_session, tmp_path):
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "software-architect.md").write_text("SA role")
    (prompts_dir / "security-architect.md").write_text("SEC role")

    ticket = make_ticket()
    registry = make_registry()
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
        patch(
            "src.services.brainstorm_coordinator.BrainstormCLIReader",
            return_value=make_mock_cli_reader(),
        ),
    ):
        settings = MagicMock()
        settings.agent_prompts_dir = str(prompts_dir)
        settings.agent_runner_mode = "claude_code"
        settings.brainstorm_agents_list = ["software-architect", "security-architect"]
        settings.brainstorm_max_rounds = 2
        settings.brainstorm_npx_prefix = "~/.local/share/brainstorm-mcp"
        settings.brainstorm_cli_timeout_seconds = 30.0
        settings.agent_timeout_for = MagicMock(return_value=300)
        mock_settings.return_value = settings

        from src.services.brainstorm_coordinator import BrainstormCoordinator

        coordinator = BrainstormCoordinator(mock_runner, registry)
        result = await coordinator.run_brainstorm(ticket, db_session)

    assert run_order[0] == "software-architect"
    assert run_order[1] == "security-architect"


async def test_two_agents_run_sequentially_with_explicit_participants(db_session, tmp_path):
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "software-architect.md").write_text("SA role")
    (prompts_dir / "security-architect.md").write_text("SEC role")

    ticket = make_ticket()
    registry = make_registry()
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
        patch(
            "src.services.brainstorm_coordinator.BrainstormCLIReader",
            return_value=make_mock_cli_reader(),
        ),
    ):
        settings = MagicMock()
        settings.agent_prompts_dir = str(prompts_dir)
        settings.agent_runner_mode = "claude_code"
        settings.brainstorm_max_rounds = 2
        settings.brainstorm_npx_prefix = "~/.local/share/brainstorm-mcp"
        settings.brainstorm_cli_timeout_seconds = 30.0
        settings.agent_timeout_for = MagicMock(return_value=300)
        mock_settings.return_value = settings

        from src.services.brainstorm_coordinator import BrainstormCoordinator

        coordinator = BrainstormCoordinator(mock_runner, registry)
        result = await coordinator.run_brainstorm(
            ticket, db_session, participants=["software-architect", "security-architect"]
        )

    assert run_order[0] == "software-architect"
    assert run_order[1] == "security-architect"


async def test_early_exit_on_first_agent_agreed(db_session, tmp_path):
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "software-architect.md").write_text("SA role")
    (prompts_dir / "security-architect.md").write_text("SEC role")

    ticket = make_ticket()
    registry = make_registry()
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
        patch(
            "src.services.brainstorm_coordinator.BrainstormCLIReader",
            return_value=make_mock_cli_reader(),
        ),
    ):
        settings = MagicMock()
        settings.agent_prompts_dir = str(prompts_dir)
        settings.agent_runner_mode = "claude_code"
        settings.brainstorm_agents_list = ["software-architect", "security-architect"]
        settings.brainstorm_max_rounds = 3
        settings.brainstorm_npx_prefix = "~/.local/share/brainstorm-mcp"
        settings.brainstorm_cli_timeout_seconds = 30.0
        settings.agent_timeout_for = MagicMock(return_value=300)
        mock_settings.return_value = settings

        from src.services.brainstorm_coordinator import BrainstormCoordinator

        coordinator = BrainstormCoordinator(mock_runner, registry)
        data = await coordinator.run_brainstorm(ticket, db_session)

    assert call_count == 1
    assert data["consensus"] == "agreed"
    assert data["concluded"] is True


async def test_max_rounds_enforced(db_session, tmp_path):
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "software-architect.md").write_text("SA role")
    (prompts_dir / "security-architect.md").write_text("SEC role")

    ticket = make_ticket()
    registry = make_registry()
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
        patch(
            "src.services.brainstorm_coordinator.BrainstormCLIReader",
            return_value=make_mock_cli_reader(),
        ),
    ):
        settings = MagicMock()
        settings.agent_prompts_dir = str(prompts_dir)
        settings.agent_runner_mode = "claude_code"
        settings.brainstorm_agents_list = ["software-architect", "security-architect"]
        settings.brainstorm_max_rounds = 2
        settings.brainstorm_npx_prefix = "~/.local/share/brainstorm-mcp"
        settings.brainstorm_cli_timeout_seconds = 30.0
        settings.agent_timeout_for = MagicMock(return_value=300)
        mock_settings.return_value = settings

        from src.services.brainstorm_coordinator import BrainstormCoordinator

        coordinator = BrainstormCoordinator(mock_runner, registry)
        data = await coordinator.run_brainstorm(ticket, db_session)

    assert call_count == 2 * 2
    assert data["rounds_completed"] == 2
    assert data["consensus"] is None


async def test_api_mode_injects_previous_responses(db_session, tmp_path):
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "software-architect.md").write_text("SA role")
    (prompts_dir / "security-architect.md").write_text("SEC role")

    ticket = make_ticket()
    registry = make_registry()
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
        patch(
            "src.services.brainstorm_coordinator.BrainstormCLIReader",
            return_value=make_mock_cli_reader(),
        ),
    ):
        settings = MagicMock()
        settings.agent_prompts_dir = str(prompts_dir)
        settings.agent_runner_mode = "api"
        settings.brainstorm_agents_list = ["software-architect", "security-architect"]
        settings.brainstorm_max_rounds = 1
        settings.brainstorm_npx_prefix = "~/.local/share/brainstorm-mcp"
        settings.brainstorm_cli_timeout_seconds = 30.0
        settings.agent_timeout_for = MagicMock(return_value=300)
        mock_settings.return_value = settings

        from src.services.brainstorm_coordinator import BrainstormCoordinator

        coordinator = BrainstormCoordinator(mock_runner, registry)
        await coordinator.run_brainstorm(ticket, db_session)

    sa_call = next(c for c in captured_prev_responses if c[0] == "software-architect")
    sec_call = next(c for c in captured_prev_responses if c[0] == "security-architect")
    assert sa_call[1] is None
    assert sec_call[1] is not None
    assert "software-architect" in sec_call[1]


# ---------------------------------------------------------------------------
# T009 — new tests for transcript + T014 — CLI failure resilience
# ---------------------------------------------------------------------------


async def test_cli_reader_called_after_round(db_session, tmp_path):
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "software-architect.md").write_text("SA role")

    ticket = make_ticket()
    registry = make_registry("df-TKT-BS-TEST")
    messages = [
        BrainstormMessage(author="software-architect", content="msg1", timestamp=""),
        BrainstormMessage(author="security-architect", content="msg2", timestamp=""),
    ]
    mock_reader = make_mock_cli_reader(messages)

    with (
        patch("src.services.brainstorm_coordinator.get_settings") as mock_settings,
        patch("src.services.brainstorm_coordinator.build_context", return_value=("ctx", "jwt")),
        patch("src.services.brainstorm_coordinator.build_context_snapshot", return_value={}),
        patch("src.services.brainstorm_coordinator.BrainstormCLIReader", return_value=mock_reader),
    ):
        settings = MagicMock()
        settings.agent_prompts_dir = str(prompts_dir)
        settings.agent_runner_mode = "claude_code"
        settings.brainstorm_agents_list = ["software-architect"]
        settings.brainstorm_max_rounds = 1
        settings.brainstorm_npx_prefix = "~/.local/share/brainstorm-mcp"
        settings.brainstorm_cli_timeout_seconds = 30.0
        settings.agent_timeout_for = MagicMock(return_value=300)
        mock_settings.return_value = settings

        from src.services.brainstorm_coordinator import BrainstormCoordinator

        coordinator = BrainstormCoordinator(MagicMock(), registry)
        coordinator._runner = AsyncMock()
        coordinator._runner.run = AsyncMock(return_value=(0, make_result_stdout()))
        result = await coordinator.run_brainstorm(ticket, db_session)

    assert "transcript" in result
    assert len(result["transcript"].messages) == 2


async def test_transcript_in_return_value(db_session, tmp_path):
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "software-architect.md").write_text("SA role")

    ticket = make_ticket()
    registry = make_registry()

    with (
        patch("src.services.brainstorm_coordinator.get_settings") as mock_settings,
        patch("src.services.brainstorm_coordinator.build_context", return_value=("ctx", "jwt")),
        patch("src.services.brainstorm_coordinator.build_context_snapshot", return_value={}),
        patch(
            "src.services.brainstorm_coordinator.BrainstormCLIReader",
            return_value=make_mock_cli_reader(),
        ),
    ):
        settings = MagicMock()
        settings.agent_prompts_dir = str(prompts_dir)
        settings.agent_runner_mode = "claude_code"
        settings.brainstorm_agents_list = ["software-architect"]
        settings.brainstorm_max_rounds = 1
        settings.brainstorm_npx_prefix = "~/.local/share/brainstorm-mcp"
        settings.brainstorm_cli_timeout_seconds = 30.0
        settings.agent_timeout_for = MagicMock(return_value=300)
        mock_settings.return_value = settings

        from src.services.brainstorm_coordinator import BrainstormCoordinator

        coordinator = BrainstormCoordinator(MagicMock(), registry)
        coordinator._runner = AsyncMock()
        coordinator._runner.run = AsyncMock(return_value=(0, make_result_stdout()))
        result = await coordinator.run_brainstorm(ticket, db_session)

    assert "transcript" in result
    assert isinstance(result["transcript"], BrainstormTranscript)


async def test_project_name_from_registry(db_session, tmp_path):
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "software-architect.md").write_text("SA role")

    ticket = make_ticket(ticket_id="TKT-XYZ")
    registry = make_registry("df-ticket-xyz")
    mock_reader = make_mock_cli_reader()

    with (
        patch("src.services.brainstorm_coordinator.get_settings") as mock_settings,
        patch("src.services.brainstorm_coordinator.build_context", return_value=("ctx", "jwt")),
        patch("src.services.brainstorm_coordinator.build_context_snapshot", return_value={}),
        patch("src.services.brainstorm_coordinator.BrainstormCLIReader", return_value=mock_reader),
    ):
        settings = MagicMock()
        settings.agent_prompts_dir = str(prompts_dir)
        settings.agent_runner_mode = "claude_code"
        settings.brainstorm_agents_list = ["software-architect"]
        settings.brainstorm_max_rounds = 1
        settings.brainstorm_npx_prefix = "~/.local/share/brainstorm-mcp"
        settings.brainstorm_cli_timeout_seconds = 30.0
        settings.agent_timeout_for = MagicMock(return_value=300)
        mock_settings.return_value = settings

        from src.services.brainstorm_coordinator import BrainstormCoordinator

        coordinator = BrainstormCoordinator(MagicMock(), registry)
        coordinator._runner = AsyncMock()
        coordinator._runner.run = AsyncMock(return_value=(0, make_result_stdout()))
        await coordinator.run_brainstorm(ticket, db_session)

    registry.brainstorm_project_name.assert_called_once_with("TKT-XYZ")
    mock_reader.read.assert_called_once_with("df-ticket-xyz")


async def test_cli_reader_failure_does_not_abort(db_session, tmp_path):
    """UpstreamError from cli_reader must not abort brainstorm round."""
    from src.core.exceptions import UpstreamError

    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "software-architect.md").write_text("SA role")

    ticket = make_ticket()
    registry = make_registry()
    failing_reader = MagicMock()
    failing_reader.read = AsyncMock(side_effect=UpstreamError("CLI down"))

    with (
        patch("src.services.brainstorm_coordinator.get_settings") as mock_settings,
        patch("src.services.brainstorm_coordinator.build_context", return_value=("ctx", "jwt")),
        patch("src.services.brainstorm_coordinator.build_context_snapshot", return_value={}),
        patch(
            "src.services.brainstorm_coordinator.BrainstormCLIReader", return_value=failing_reader
        ),
    ):
        settings = MagicMock()
        settings.agent_prompts_dir = str(prompts_dir)
        settings.agent_runner_mode = "claude_code"
        settings.brainstorm_agents_list = ["software-architect"]
        settings.brainstorm_max_rounds = 1
        settings.brainstorm_npx_prefix = "~/.local/share/brainstorm-mcp"
        settings.brainstorm_cli_timeout_seconds = 30.0
        settings.agent_timeout_for = MagicMock(return_value=300)
        mock_settings.return_value = settings

        from src.services.brainstorm_coordinator import BrainstormCoordinator

        coordinator = BrainstormCoordinator(MagicMock(), registry)
        coordinator._runner = AsyncMock()
        coordinator._runner.run = AsyncMock(return_value=(0, make_result_stdout()))
        result = await coordinator.run_brainstorm(ticket, db_session)

    assert result["transcript"].messages == []
    assert result["transcript"].consensus == "inconclusive"
