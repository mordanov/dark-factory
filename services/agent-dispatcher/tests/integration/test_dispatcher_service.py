"""Integration tests for DispatcherService."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from src.repositories.run_repo import AgentRunRepository
from src.schemas.schemas import AgentResult


def make_ticket(
    ticket_id="TKT-DS-001",
    project_id="proj-1",
    agent_id="backend",
    fsm_status="implementation",
    ticket_type="feature",
):
    return MagicMock(
        id=ticket_id,
        project_id=project_id,
        assigned_agent=agent_id,
        fsm_status=fsm_status,
        ticket_type=ticket_type,
        title="Test ticket",
        description="Description",
    )


async def test_single_agent_run_success(db_session, tmp_path):
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "backend.md").write_text("You are backend.")

    ticket = make_ticket()
    result_json = '{"status": "completed", "summary": "done", "tm_comment": "Done!"}'
    stdout = f"[RESULT]\n{result_json}\n[/RESULT]"

    with (
        patch("src.services.dispatcher_service.get_settings") as mock_settings,
        patch("src.services.dispatcher_service.get_runner") as mock_get_runner,
        patch("src.services.dispatcher_service.Reporter") as mock_reporter_cls,
        patch(
            "src.services.dispatcher_service.build_context",
            return_value=("context text", "jwt-token"),
        ),
        patch(
            "src.services.dispatcher_service.build_context_snapshot",
            return_value={"ticket_id": "TKT-DS-001"},
        ),
    ):
        settings = MagicMock()
        settings.agent_prompts_dir = str(prompts_dir)
        settings.agent_runner_mode = "claude_code"
        settings.agent_timeout_default = 300
        settings.agent_timeout_for = MagicMock(return_value=300)
        mock_settings.return_value = settings

        mock_runner = AsyncMock()
        mock_runner.run = AsyncMock(return_value=(0, stdout))
        mock_get_runner.return_value = mock_runner

        mock_reporter = AsyncMock()
        mock_reporter.report_result = AsyncMock()
        mock_reporter_cls.return_value = mock_reporter

        from src.services.dispatcher_service import process_ticket

        await process_ticket(ticket, db_session)

    mock_reporter.report_result.assert_called_once()
    call_kwargs = mock_reporter.report_result.call_args
    result = call_kwargs.kwargs.get("result") or call_kwargs.args[2]
    assert result.status == "completed"


async def test_missing_prompt_file_marks_failed(db_session, tmp_path):
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    # no backend.md

    ticket = make_ticket(ticket_id="TKT-DS-002")

    with (
        patch("src.services.dispatcher_service.get_settings") as mock_settings,
        patch("src.services.dispatcher_service.get_runner") as mock_get_runner,
        patch("src.services.dispatcher_service.Reporter") as mock_reporter_cls,
        patch("src.services.dispatcher_service.build_context", return_value=("ctx", "jwt-token")),
        patch("src.services.dispatcher_service.build_context_snapshot", return_value={}),
    ):
        settings = MagicMock()
        settings.agent_prompts_dir = str(prompts_dir)
        settings.agent_runner_mode = "claude_code"
        settings.agent_timeout_for = MagicMock(return_value=300)
        mock_settings.return_value = settings

        mock_runner = AsyncMock()
        mock_get_runner.return_value = mock_runner

        mock_reporter = AsyncMock()
        mock_reporter.report_result = AsyncMock()
        mock_reporter_cls.return_value = mock_reporter

        from src.services.dispatcher_service import process_ticket

        await process_ticket(ticket, db_session)

    mock_reporter.report_result.assert_called_once()
    result = (
        mock_reporter.report_result.call_args.kwargs.get("result")
        or mock_reporter.report_result.call_args.args[2]
    )
    assert result.status in ("needs_review", "failed", "blocked")


async def test_runner_nonzero_exit_marks_failed(db_session, tmp_path):
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "backend.md").write_text("You are backend.")

    ticket = make_ticket(ticket_id="TKT-DS-003")

    with (
        patch("src.services.dispatcher_service.get_settings") as mock_settings,
        patch("src.services.dispatcher_service.get_runner") as mock_get_runner,
        patch("src.services.dispatcher_service.Reporter") as mock_reporter_cls,
        patch("src.services.dispatcher_service.build_context", return_value=("ctx", "jwt-token")),
        patch("src.services.dispatcher_service.build_context_snapshot", return_value={}),
    ):
        settings = MagicMock()
        settings.agent_prompts_dir = str(prompts_dir)
        settings.agent_runner_mode = "claude_code"
        settings.agent_timeout_for = MagicMock(return_value=300)
        mock_settings.return_value = settings

        mock_runner = AsyncMock()
        mock_runner.run = AsyncMock(return_value=(-1, "error output"))
        mock_get_runner.return_value = mock_runner

        mock_reporter = AsyncMock()
        mock_reporter.report_result = AsyncMock()
        mock_reporter_cls.return_value = mock_reporter

        from src.services.dispatcher_service import process_ticket

        await process_ticket(ticket, db_session)

    mock_reporter.report_result.assert_called_once()
    result = (
        mock_reporter.report_result.call_args.kwargs.get("result")
        or mock_reporter.report_result.call_args.args[2]
    )
    assert result.status in ("needs_review", "failed")


# ── Phase 4 (US2): Graceful failure handling tests ──────────────────────────


async def test_runner_timeout_marks_timed_out(db_session, tmp_path):
    """Runner timeout → timed_out status, TM comment posted, Orchestrator triggered."""
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "backend.md").write_text("You are backend.")

    ticket = make_ticket(ticket_id="TKT-DS-TIMEOUT")

    with (
        patch("src.services.dispatcher_service.get_settings") as mock_settings,
        patch("src.services.dispatcher_service.get_runner") as mock_get_runner,
        patch("src.services.dispatcher_service.Reporter") as mock_reporter_cls,
        patch("src.services.dispatcher_service.build_context", return_value=("ctx", "jwt-token")),
        patch("src.services.dispatcher_service.build_context_snapshot", return_value={}),
    ):
        settings = MagicMock()
        settings.agent_prompts_dir = str(prompts_dir)
        settings.agent_runner_mode = "claude_code"
        settings.agent_timeout_for = MagicMock(return_value=1)
        mock_settings.return_value = settings

        async def slow_run(*args, **kwargs):
            await asyncio.sleep(10)
            return (0, "")

        mock_runner = AsyncMock()
        mock_runner.run = slow_run
        mock_get_runner.return_value = mock_runner

        mock_reporter = AsyncMock()
        mock_reporter.report_result = AsyncMock()
        mock_reporter_cls.return_value = mock_reporter

        from src.services.dispatcher_service import process_ticket

        await process_ticket(ticket, db_session)

    mock_reporter.report_result.assert_called_once()
    result = (
        mock_reporter.report_result.call_args.kwargs.get("result")
        or mock_reporter.report_result.call_args.args[2]
    )
    assert result.status in ("needs_review", "timed_out")

    repo = AgentRunRepository(db_session)
    runs, total = await repo.list_all(ticket_id="TKT-DS-TIMEOUT")
    assert total >= 1
    assert any(r.status == "timed_out" for r in runs)


async def test_no_result_block_marks_needs_review(db_session, tmp_path):
    """Agent exits 0 with no [RESULT] block → needs_review, raw stdout as TM comment."""
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "backend.md").write_text("You are backend.")

    ticket = make_ticket(ticket_id="TKT-DS-NOBLOCK")
    raw_stdout = "I did some work but forgot to format the result block"

    with (
        patch("src.services.dispatcher_service.get_settings") as mock_settings,
        patch("src.services.dispatcher_service.get_runner") as mock_get_runner,
        patch("src.services.dispatcher_service.Reporter") as mock_reporter_cls,
        patch("src.services.dispatcher_service.build_context", return_value=("ctx", "jwt-token")),
        patch("src.services.dispatcher_service.build_context_snapshot", return_value={}),
    ):
        settings = MagicMock()
        settings.agent_prompts_dir = str(prompts_dir)
        settings.agent_runner_mode = "claude_code"
        settings.agent_timeout_for = MagicMock(return_value=300)
        mock_settings.return_value = settings

        mock_runner = AsyncMock()
        mock_runner.run = AsyncMock(return_value=(0, raw_stdout))
        mock_get_runner.return_value = mock_runner

        mock_reporter = AsyncMock()
        mock_reporter.report_result = AsyncMock()
        mock_reporter_cls.return_value = mock_reporter

        from src.services.dispatcher_service import process_ticket

        await process_ticket(ticket, db_session)

    mock_reporter.report_result.assert_called_once()
    result = (
        mock_reporter.report_result.call_args.kwargs.get("result")
        or mock_reporter.report_result.call_args.args[2]
    )
    assert result.status == "needs_review"
    assert result.tm_comment == raw_stdout[:2000]


async def test_architecture_review_routes_to_brainstorm(db_session, tmp_path):
    """architecture_review ticket routes to BrainstormCoordinator."""
    ticket = make_ticket(
        ticket_id="TKT-DS-ARCH",
        fsm_status="architecture_review",
        ticket_type="feature",
    )

    mock_result = AgentResult(status="completed", tm_comment="Arch review done")

    with (
        patch("src.services.dispatcher_service.get_settings") as mock_settings,
        patch("src.services.dispatcher_service.get_runner") as mock_get_runner,
        patch("src.services.dispatcher_service.Reporter") as mock_reporter_cls,
        patch("src.services.dispatcher_service._run_brainstorm") as mock_run_brainstorm,
    ):
        settings = MagicMock()
        settings.agent_runner_mode = "claude_code"
        mock_settings.return_value = settings

        mock_runner = AsyncMock()
        mock_get_runner.return_value = mock_runner

        mock_reporter = AsyncMock()
        mock_reporter.report_result = AsyncMock()
        mock_reporter_cls.return_value = mock_reporter

        mock_run_brainstorm.return_value = None

        from src.services.dispatcher_service import process_ticket

        await process_ticket(ticket, db_session)

    mock_run_brainstorm.assert_called_once()
    mock_reporter.report_result.assert_not_called()


async def test_non_architecture_review_does_not_invoke_brainstorm(db_session, tmp_path):
    """Non-architecture_review ticket does NOT invoke BrainstormCoordinator."""
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "backend.md").write_text("You are backend.")

    ticket = make_ticket(
        ticket_id="TKT-DS-NONARCH",
        fsm_status="implementation",
        ticket_type="feature",
    )

    brainstorm_called = False

    with (
        patch("src.services.dispatcher_service.get_settings") as mock_settings,
        patch("src.services.dispatcher_service.get_runner") as mock_get_runner,
        patch("src.services.dispatcher_service.Reporter") as mock_reporter_cls,
        patch("src.services.dispatcher_service.build_context", return_value=("ctx", "jwt-token")),
        patch("src.services.dispatcher_service.build_context_snapshot", return_value={}),
        patch("src.services.dispatcher_service._run_brainstorm") as mock_run_brainstorm,
    ):
        settings = MagicMock()
        settings.agent_prompts_dir = str(prompts_dir)
        settings.agent_runner_mode = "claude_code"
        settings.agent_timeout_for = MagicMock(return_value=300)
        mock_settings.return_value = settings

        mock_runner = AsyncMock()
        mock_runner.run = AsyncMock(return_value=(0, '[RESULT]\n{"status":"completed"}\n[/RESULT]'))
        mock_get_runner.return_value = mock_runner

        mock_reporter = AsyncMock()
        mock_reporter.report_result = AsyncMock()
        mock_reporter_cls.return_value = mock_reporter

        mock_run_brainstorm.return_value = None

        from src.services.dispatcher_service import process_ticket

        await process_ticket(ticket, db_session)

    mock_run_brainstorm.assert_not_called()


# ── SEC-07/SEC-08: Path traversal and unknown agent_id rejection ─────────────


async def test_unknown_agent_id_marks_failed(db_session, tmp_path):
    """SEC-07: unknown agent_id not in VALID_AGENT_IDS → failed run, reporter called."""
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()

    ticket = make_ticket(ticket_id="TKT-DS-SEC07", agent_id="unknown_agent")

    with (
        patch("src.services.dispatcher_service.get_settings") as mock_settings,
        patch("src.services.dispatcher_service.get_runner") as mock_get_runner,
        patch("src.services.dispatcher_service.Reporter") as mock_reporter_cls,
        patch("src.services.dispatcher_service.build_context", return_value=("ctx", "jwt-token")),
        patch("src.services.dispatcher_service.build_context_snapshot", return_value={}),
    ):
        settings = MagicMock()
        settings.agent_prompts_dir = str(prompts_dir)
        settings.agent_runner_mode = "claude_code"
        settings.agent_timeout_for = MagicMock(return_value=300)
        mock_settings.return_value = settings

        mock_runner = AsyncMock()
        mock_get_runner.return_value = mock_runner

        mock_reporter = AsyncMock()
        mock_reporter.report_result = AsyncMock()
        mock_reporter_cls.return_value = mock_reporter

        from src.services.dispatcher_service import process_ticket

        await process_ticket(ticket, db_session)

    mock_reporter.report_result.assert_called_once()
    result = (
        mock_reporter.report_result.call_args.kwargs.get("result")
        or mock_reporter.report_result.call_args.args[2]
    )
    assert result.status in ("needs_review", "failed", "blocked")
    mock_runner.run.assert_not_called()


async def test_traversal_agent_id_marks_failed(db_session, tmp_path):
    """SEC-08: traversal string agent_id rejected before any filesystem access."""
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()

    ticket = make_ticket(ticket_id="TKT-DS-SEC08", agent_id="../../../etc/passwd")

    with (
        patch("src.services.dispatcher_service.get_settings") as mock_settings,
        patch("src.services.dispatcher_service.get_runner") as mock_get_runner,
        patch("src.services.dispatcher_service.Reporter") as mock_reporter_cls,
        patch("src.services.dispatcher_service.build_context", return_value=("ctx", "jwt-token")),
        patch("src.services.dispatcher_service.build_context_snapshot", return_value={}),
    ):
        settings = MagicMock()
        settings.agent_prompts_dir = str(prompts_dir)
        settings.agent_runner_mode = "claude_code"
        settings.agent_timeout_for = MagicMock(return_value=300)
        mock_settings.return_value = settings

        mock_runner = AsyncMock()
        mock_get_runner.return_value = mock_runner

        mock_reporter = AsyncMock()
        mock_reporter.report_result = AsyncMock()
        mock_reporter_cls.return_value = mock_reporter

        from src.services.dispatcher_service import process_ticket

        await process_ticket(ticket, db_session)

    mock_reporter.report_result.assert_called_once()
    result = (
        mock_reporter.report_result.call_args.kwargs.get("result")
        or mock_reporter.report_result.call_args.args[2]
    )
    assert result.status in ("needs_review", "failed", "blocked")
    mock_runner.run.assert_not_called()
