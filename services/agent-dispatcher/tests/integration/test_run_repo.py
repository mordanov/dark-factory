"""Integration tests for AgentRunRepository."""

from __future__ import annotations

import pytest
from src.repositories.run_repo import AgentRunRepository


@pytest.fixture
async def repo(db_session):
    return AgentRunRepository(db_session)


async def test_create_and_lifecycle(repo):
    run = await repo.create(
        ticket_id="TKT-001",
        project_id="proj-1",
        agent_id="backend",
        runner_mode="claude_code",
        context_snapshot={"ticket_id": "TKT-001"},
    )
    assert run.id is not None
    assert run.status == "pending"

    await repo.mark_running(run.id)
    fetched = await repo.get_by_id(run.id)
    assert fetched.status == "running"
    assert fetched.started_at is not None

    await repo.mark_done(run.id, {"status": "completed"}, "stdout output")
    fetched = await repo.get_by_id(run.id)
    assert fetched.status == "completed"
    assert fetched.finished_at is not None


async def test_has_running_true_for_running(repo):
    run = await repo.create(
        ticket_id="TKT-002",
        project_id="proj-1",
        agent_id="backend",
        runner_mode="api",
        context_snapshot={},
    )
    await repo.mark_running(run.id)
    assert await repo.has_running("TKT-002") is True


async def test_has_running_false_for_completed(repo):
    run = await repo.create(
        ticket_id="TKT-003",
        project_id="proj-1",
        agent_id="backend",
        runner_mode="api",
        context_snapshot={},
    )
    await repo.mark_running(run.id)
    await repo.mark_done(run.id, {}, "")
    assert await repo.has_running("TKT-003") is False


async def test_list_all_filters_by_ticket_id(repo):
    await repo.create(
        ticket_id="TKT-FILTER-1",
        project_id="proj-1",
        agent_id="backend",
        runner_mode="api",
        context_snapshot={},
    )
    await repo.create(
        ticket_id="TKT-FILTER-2",
        project_id="proj-1",
        agent_id="backend",
        runner_mode="api",
        context_snapshot={},
    )
    items, total = await repo.list_all(ticket_id="TKT-FILTER-1")
    assert all(r.ticket_id == "TKT-FILTER-1" for r in items)


async def test_list_all_filters_by_status(repo):
    run = await repo.create(
        ticket_id="TKT-STATUS-1",
        project_id="proj-1",
        agent_id="backend",
        runner_mode="api",
        context_snapshot={},
    )
    await repo.mark_running(run.id)
    items, _ = await repo.list_all(status="running")
    running_ids = {r.id for r in items}
    assert run.id in running_ids


async def test_sweep_orphaned_running(repo):
    run1 = await repo.create(
        ticket_id="TKT-ORPHAN-1",
        project_id="proj-1",
        agent_id="backend",
        runner_mode="claude_code",
        context_snapshot={},
    )
    run2 = await repo.create(
        ticket_id="TKT-ORPHAN-2",
        project_id="proj-1",
        agent_id="backend",
        runner_mode="claude_code",
        context_snapshot={},
    )
    await repo.mark_running(run1.id)
    await repo.mark_running(run2.id)

    pairs = await repo.sweep_orphaned_running()
    ticket_ids = [t for t, _ in pairs]
    assert "TKT-ORPHAN-1" in ticket_ids
    assert "TKT-ORPHAN-2" in ticket_ids

    r1 = await repo.get_by_id(run1.id)
    assert r1.status == "needs_review"
    assert r1.error_message == "Service restarted; run orphaned"


async def test_sweep_orphaned_noop_when_no_running(repo):
    ticket_ids = await repo.sweep_orphaned_running()
    assert ticket_ids == []
