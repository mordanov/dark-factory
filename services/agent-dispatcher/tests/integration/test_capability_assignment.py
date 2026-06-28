"""Integration tests — US1: Capability-Based Assignment."""

from __future__ import annotations

from dataclasses import dataclass, field
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from src.repositories.run_repo import AgentRunRepository
from src.repositories.worker_repository import AgentWorkerRepository
from src.schemas.schemas import AgentResult
from src.services.capability_registry import AgentCapability

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_ticket(
    ticket_id="TKT-CAP-001",
    project_id="proj-cap",
    agent_id="backend",
    fsm_status="backend_development",
    ticket_type="feature",
):
    return MagicMock(
        id=ticket_id,
        project_id=project_id,
        assigned_agent=agent_id,
        fsm_status=fsm_status,
        ticket_type=ticket_type,
        title="Capability test ticket",
        description="Test",
    )


def _make_backend_capability():
    return AgentCapability(
        role_id="backend",
        display_name="Backend Engineer",
        skill_file="backend.md",
        coordinator=False,
        capabilities=["python_backend", "fastapi"],
        fsm_ownership=["backend_development"],
        preferred_for=[],
        brainstorm_also_for=[],
        brainstorm_role="contributor",
        confidence={"python_backend": 95, "fastapi": 90},
    )


async def _run_process_ticket(ticket, db, required_capabilities=None):
    """Thin wrapper that wires mocks and calls process_ticket."""
    import asyncio
    from pathlib import Path

    from src.services.dispatcher_service import process_ticket

    prompts_dir = Path("/tmp/test_prompts_cap")
    prompts_dir.mkdir(parents=True, exist_ok=True)
    (prompts_dir / "backend.md").write_text("You are backend.")

    result_json = '{"status": "completed", "summary": "done", "tm_comment": "Done!"}'
    stdout = f"[RESULT]\n{result_json}\n[/RESULT]"

    with (
        patch("src.services.dispatcher_service.get_settings") as mock_settings,
        patch("src.services.dispatcher_service.get_runner") as mock_get_runner,
        patch("src.services.dispatcher_service.Reporter") as mock_reporter_cls,
        patch("src.services.dispatcher_service.build_context", return_value=("ctx", "jwt")),
        patch(
            "src.services.dispatcher_service.build_context_snapshot",
            return_value={"ticket_id": ticket.id},
        ),
        patch(
            "src.services.dispatcher_service._write_credentials",
            new_callable=AsyncMock,
            return_value="",
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
        mock_reporter_cls.return_value = mock_reporter

        await process_ticket(ticket, db, required_capabilities=required_capabilities)

    return mock_reporter


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_capability_based_assignment_resolves_idle_worker(db_session):
    """When a matching idle worker exists, process_ticket picks it and logs the capability record."""
    backend_cap = _make_backend_capability()

    worker_repo = AgentWorkerRepository(db_session)
    worker = await worker_repo.create(
        role_id="backend",
        version="1.0",
        capabilities_snapshot={"python_backend": 95},
    )
    await db_session.commit()

    with patch("src.services.worker_service.get_registry") as mock_reg:
        mock_reg.return_value.get_by_capability.return_value = [backend_cap]
        mock_reg.return_value.get_by_role_id.return_value = backend_cap

        ticket = make_ticket()
        reporter = await _run_process_ticket(
            ticket, db_session, required_capabilities=["python_backend"]
        )

    # Reporter was called — confirms process_ticket completed
    reporter.report_result.assert_called_once()
    call_kwargs = reporter.report_result.call_args.kwargs
    result: AgentResult = call_kwargs["result"]
    assert result.matched_capability_record is not None
    assert result.matched_capability_record["role_id"] == "backend"


async def test_capability_based_assignment_falls_back_when_no_idle_worker(db_session):
    """When no idle worker is found, dispatcher falls back to static assignment."""
    backend_cap = _make_backend_capability()

    # No workers registered — list_all returns empty
    with patch("src.services.worker_service.get_registry") as mock_reg:
        mock_reg.return_value.get_by_capability.return_value = [backend_cap]
        mock_reg.return_value.get_by_role_id.return_value = backend_cap

        ticket = make_ticket()
        reporter = await _run_process_ticket(
            ticket, db_session, required_capabilities=["python_backend"]
        )

    reporter.report_result.assert_called_once()
    call_kwargs = reporter.report_result.call_args.kwargs
    result: AgentResult = call_kwargs["result"]
    # Fallback: matched_capability_record is None
    assert result.matched_capability_record is None


async def test_empty_required_capabilities_uses_static_assignment(db_session):
    """Empty required_capabilities list → static assignment, no capability resolution attempted."""
    ticket = make_ticket()
    with patch("src.services.worker_service.AgentWorkerService") as mock_svc_cls:
        reporter = await _run_process_ticket(ticket, db_session, required_capabilities=[])
        # WorkerService should never be called for capability resolution
        mock_svc_cls.assert_not_called()

    reporter.report_result.assert_called_once()
    result = reporter.report_result.call_args.kwargs["result"]
    assert result.matched_capability_record is None


async def test_no_required_capabilities_kwarg_uses_static_assignment(db_session):
    """Calling process_ticket with no required_capabilities → unchanged static behavior."""
    ticket = make_ticket()
    reporter = await _run_process_ticket(ticket, db_session, required_capabilities=None)

    reporter.report_result.assert_called_once()
    result = reporter.report_result.call_args.kwargs["result"]
    assert result.matched_capability_record is None


async def test_capability_fallback_on_unknown_capability(db_session):
    """When registry returns no agents for the required capability, fall back silently."""
    with patch("src.services.worker_service.get_registry") as mock_reg:
        mock_reg.return_value.get_by_capability.return_value = []  # no match

        ticket = make_ticket()
        reporter = await _run_process_ticket(
            ticket, db_session, required_capabilities=["exotic_unknown_skill"]
        )

    reporter.report_result.assert_called_once()
    result = reporter.report_result.call_args.kwargs["result"]
    assert result.matched_capability_record is None
