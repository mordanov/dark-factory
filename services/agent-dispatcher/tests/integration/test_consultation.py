"""Integration tests — US3: Peer Consultation."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from src.repositories.worker_repository import AgentWorkerRepository
from src.schemas.schemas import ConsultRequest
from src.services.capability_registry import AgentCapability
from src.services.consultation_service import (
    ConsultationService,
    ConsultationTimeoutError,
    PeerNotAvailableError,
)


def _security_cap():
    return AgentCapability(
        role_id="security-architect",
        display_name="Security Architect",
        skill_file="security-architect.md",
        coordinator=False,
        capabilities=["security_assessment"],
        fsm_ownership=["security_review"],
        preferred_for=[],
        brainstorm_also_for=[],
        brainstorm_role="contributor",
    )


def _make_request(ticket_id="TICKET-001", run_id=None):
    return ConsultRequest(
        requesting_role_id="software-architect",
        run_id=run_id or uuid.uuid4(),
        ticket_id=ticket_id,
        required_peer_capabilities=["security_assessment"],
        question="Should we use RLS or app-layer filtering?",
        context_summary="PostgreSQL 16, multi-tenant SaaS",
        timeout_seconds=10,
    )


async def _register_idle_worker(db_session, role_id="security-architect"):
    repo = AgentWorkerRepository(db_session)
    worker = await repo.create(role_id, "1.0", {"security_assessment": 90})
    await db_session.commit()
    return worker


async def test_consultation_returns_answer(db_session):
    """Happy path: peer available, answer returned, WM entries written."""
    from src.repositories.run_repo import AgentRunRepository

    run_repo = AgentRunRepository(db_session)
    run = await run_repo.create(
        ticket_id="TICKET-001",
        project_id="proj-1",
        agent_id="software-architect",
        runner_mode="claude_code",
        context_snapshot={},
    )
    await db_session.commit()

    worker = await _register_idle_worker(db_session)
    sec_cap = _security_cap()

    with (
        patch("src.services.worker_service.get_registry") as mock_reg,
        patch(
            "src.services.consultation_service._call_peer_agent",
            new=AsyncMock(return_value="Use RLS for true isolation."),
        ),
    ):
        mock_reg.return_value.get_by_capability.return_value = [sec_cap]
        mock_reg.return_value.get_by_role_id.return_value = sec_cap

        svc = ConsultationService(db_session)
        request = _make_request(run_id=run.id)
        response = await svc.consult(request)
        await db_session.commit()

    assert response.peer_role_id == "security-architect"
    assert "RLS" in response.answer
    assert response.latency_ms >= 0
    assert response.peer_capability_record["role_id"] == "security-architect"


async def test_consultation_auto_writes_to_working_memory(db_session):
    """Successful consultation writes question + answer WM entries."""
    from src.repositories.run_repo import AgentRunRepository
    from src.repositories.working_memory_repository import WorkingMemoryRepository

    run_repo = AgentRunRepository(db_session)
    run = await run_repo.create(
        ticket_id="TICKET-WM-TEST",
        project_id="proj-1",
        agent_id="software-architect",
        runner_mode="claude_code",
        context_snapshot={},
    )
    await db_session.commit()

    await _register_idle_worker(db_session)
    sec_cap = _security_cap()

    with (
        patch("src.services.worker_service.get_registry") as mock_reg,
        patch(
            "src.services.consultation_service._call_peer_agent",
            new=AsyncMock(return_value="Use RLS."),
        ),
    ):
        mock_reg.return_value.get_by_capability.return_value = [sec_cap]
        mock_reg.return_value.get_by_role_id.return_value = sec_cap

        svc = ConsultationService(db_session)
        request = _make_request(ticket_id="TICKET-WM-TEST", run_id=run.id)
        await svc.consult(request)
        await db_session.commit()

    wm_repo = WorkingMemoryRepository(db_session)
    entries = await wm_repo.list_for_ticket("TICKET-WM-TEST")
    entry_types = {e.entry_type for e in entries}
    assert "question" in entry_types
    assert "answer" in entry_types
    assert any("consultation" in e.tags for e in entries)


async def test_consultation_raises_when_no_peer(db_session):
    """No idle peer → PeerNotAvailableError."""
    sec_cap = _security_cap()
    with patch("src.services.worker_service.get_registry") as mock_reg:
        mock_reg.return_value.get_by_capability.return_value = [sec_cap]
        # No workers registered → resolve_capable_worker returns None

        svc = ConsultationService(db_session)
        request = _make_request()
        with pytest.raises(PeerNotAvailableError):
            await svc.consult(request)


async def test_consultation_raises_on_timeout(db_session):
    """Peer runner exceeds timeout → ConsultationTimeoutError."""
    import asyncio

    await _register_idle_worker(db_session)
    sec_cap = _security_cap()

    async def slow_peer(*_args, **_kwargs):
        await asyncio.sleep(99)
        return "too late"

    with (
        patch("src.services.worker_service.get_registry") as mock_reg,
        patch("src.services.consultation_service._call_peer_agent", new=slow_peer),
    ):
        mock_reg.return_value.get_by_capability.return_value = [sec_cap]
        mock_reg.return_value.get_by_role_id.return_value = sec_cap

        svc = ConsultationService(db_session)
        request = ConsultRequest(
            requesting_role_id="software-architect",
            run_id=uuid.uuid4(),
            ticket_id="TICKET-TIMEOUT",
            required_peer_capabilities=["security_assessment"],
            question="Will this time out?",
            timeout_seconds=1,
        )
        with pytest.raises(ConsultationTimeoutError):
            await svc.consult(request)


async def test_consultation_does_not_change_requester_status(db_session):
    """Consultation is lightweight; requesting worker status must not change."""
    repo = AgentWorkerRepository(db_session)
    requester = await repo.create("software-architect", "1.0", {})
    await repo.update_status(requester.id, "busy")
    await db_session.commit()

    await _register_idle_worker(db_session)
    sec_cap = _security_cap()

    with (
        patch("src.services.worker_service.get_registry") as mock_reg,
        patch(
            "src.services.consultation_service._call_peer_agent",
            new=AsyncMock(return_value="RLS is better."),
        ),
    ):
        mock_reg.return_value.get_by_capability.return_value = [sec_cap]
        mock_reg.return_value.get_by_role_id.return_value = sec_cap

        from src.repositories.run_repo import AgentRunRepository

        run_repo = AgentRunRepository(db_session)
        run = await run_repo.create(
            ticket_id="TICKET-REQUESTER-CHECK",
            project_id="proj-1",
            agent_id="software-architect",
            runner_mode="claude_code",
            context_snapshot={},
        )
        await db_session.commit()

        svc = ConsultationService(db_session)
        request = _make_request(ticket_id="TICKET-REQUESTER-CHECK", run_id=run.id)
        await svc.consult(request)
        await db_session.commit()

    refreshed = await repo.get_by_id(requester.id)
    assert refreshed.status == "busy"  # unchanged
