"""Integration tests — OrchestratorService end-to-end with mocked LLM and TM."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from src.repositories.job_repo import JobRepository
from src.schemas.schemas import AgentBriefing, DecisionDetail, OrchestratorDecision, TmTicket
from src.services.orchestrator_service import OrchestratorService


def make_decision(action="ADVANCE", to_state="specification", agent="project_manager"):
    return OrchestratorDecision(
        orchestrator_version="1.1",
        ticket_id="t-1",
        timestamp="2024-01-01T00:00:00Z",
        decision=DecisionDetail(
            action=action,
            from_state="triage",
            to_state=to_state,
            assigned_agent=agent,
            blocked_reason=None if action != "BLOCK" else "Gate failed",
            override_logged=False,
        ),
        agent_briefing=AgentBriefing(
            agent_id=agent,
            task_summary="Write the specification document",
            relevant_files=[],
            constraints=["All endpoints must be async"],
            acceptance_criteria=["AC1"],
            context_refs={},
        )
        if action == "ADVANCE"
        else None,
        gate_results=[],
        adr=None,
        dependency_check={"all_clear": True, "blocking_dependencies": []},
        context_distiller_trigger=(to_state == "done"),
        audit_entry={"event": action, "actor": "orchestrator", "details": "ok"},
        errors=[],
    )


@pytest.fixture
def svc(db, mock_tm, mock_doc_store):
    return OrchestratorService(db, mock_tm, mock_doc_store)


@pytest.mark.asyncio
async def test_process_job_advance(db, svc, mock_tm, mock_doc_store):
    # Create a job
    repo = JobRepository(db)
    job = await repo.create(
        job_type="orchestrate",
        ticket_id="t-1",
        project_id="p-1",
        triggered_by="human",
        payload={},
    )

    with patch(
        "src.services.orchestrator_service.call_orchestrator_llm",
        AsyncMock(return_value=make_decision("ADVANCE", "specification")),
    ):
        result = await svc.process_job(job.id)

    assert result["action"] == "ADVANCE"
    assert result["to_state"] == "specification"
    mock_tm.update_fsm.assert_awaited()

    fetched = await repo.get_by_id(job.id)
    assert fetched.status == "done"


@pytest.mark.asyncio
async def test_process_job_block(db, svc, mock_tm, mock_doc_store):
    repo = JobRepository(db)
    job = await repo.create(
        job_type="orchestrate",
        ticket_id="t-1",
        project_id="p-1",
        triggered_by="human",
        payload={},
    )

    with patch(
        "src.services.orchestrator_service.call_orchestrator_llm",
        AsyncMock(return_value=make_decision("BLOCK", None)),
    ):
        result = await svc.process_job(job.id)

    assert result["action"] == "BLOCK"
    call_kwargs = mock_tm.update_fsm.call_args.kwargs
    assert call_kwargs.get("fsm_status") == "BLOCKED"


@pytest.mark.asyncio
async def test_process_job_saves_adr(db, svc, mock_tm, mock_doc_store):
    repo = JobRepository(db)
    job = await repo.create(
        job_type="orchestrate",
        ticket_id="t-1",
        project_id="p-1",
        triggered_by="human",
        payload={},
    )

    decision = make_decision("GENERATE_ADR", "implementation")
    decision.decision.action = "GENERATE_ADR"
    decision.adr = "# ADR-001: Use Postgres\n\n## Decision\nPostgres."

    with patch(
        "src.services.orchestrator_service.call_orchestrator_llm", AsyncMock(return_value=decision)
    ):
        await svc.process_job(job.id)

    mock_doc_store.save_adr.assert_awaited_once()


@pytest.mark.asyncio
async def test_process_job_triggers_distiller(db, svc, mock_tm, mock_doc_store):
    repo = JobRepository(db)
    job = await repo.create(
        job_type="orchestrate",
        ticket_id="t-1",
        project_id="p-1",
        triggered_by="human",
        payload={},
    )

    decision = make_decision("ADVANCE", "done")
    decision.context_distiller_trigger = True

    with patch(
        "src.services.orchestrator_service.call_orchestrator_llm", AsyncMock(return_value=decision)
    ):
        await svc.process_job(job.id)

    # A new distill job should have been enqueued
    jobs, _ = await repo.list_all(status="pending")
    distill_jobs = [j for j in jobs if j.job_type == "distill"]
    assert len(distill_jobs) == 1


@pytest.mark.asyncio
async def test_process_job_needs_estimation_no_llm(db, mock_doc_store):
    """Tickets with needs-estimation in backlog should WAIT without calling LLM."""
    # Override TM to return a ticket with the tag
    mock_tm = MagicMock()
    mock_tm.get_ticket_full = AsyncMock(
        return_value={
            "id": "t-estim",
            "project_id": "p-1",
            "title": "T",
            "description": "D",
            "ticket_type": "feature",
            "tags": ["needs-estimation"],
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
    )
    mock_tm.update_fsm = AsyncMock(return_value={})
    mock_tm.get_fsm_status_batch = AsyncMock(return_value={})

    repo = JobRepository(db)
    job = await repo.create(
        job_type="orchestrate",
        ticket_id="t-estim",
        project_id="p-1",
        triggered_by="human",
        payload={},
    )
    svc = OrchestratorService(db, mock_tm, mock_doc_store)

    with patch("src.services.orchestrator_service.call_orchestrator_llm") as llm_mock:
        result = await svc.process_job(job.id)
        llm_mock.assert_not_called()

    assert result["action"] == "WAIT"


@pytest.mark.asyncio
async def test_process_job_failed_on_llm_error(db, mock_tm, mock_doc_store):
    from src.core.exceptions import UpstreamError

    repo = JobRepository(db)
    job = await repo.create(
        job_type="orchestrate",
        ticket_id="t-1",
        project_id="p-1",
        triggered_by="human",
        payload={},
    )
    svc = OrchestratorService(db, mock_tm, mock_doc_store)

    with patch(
        "src.services.orchestrator_service.call_orchestrator_llm",
        AsyncMock(side_effect=UpstreamError("LLM down")),
    ):
        with pytest.raises(UpstreamError):
            await svc.process_job(job.id)

    fetched = await repo.get_by_id(job.id)
    assert fetched.status == "failed"
    assert "LLM down" in fetched.error_message
