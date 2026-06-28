"""Integration tests — US4: Append-only shared working memory per ticket."""

from __future__ import annotations

import uuid

import pytest
from src.repositories.working_memory_repository import WorkingMemoryRepository
from src.services.working_memory_service import WorkingMemoryService


async def _make_run(db_session, ticket_id="TICKET-WM-001"):
    from src.repositories.run_repo import AgentRunRepository

    repo = AgentRunRepository(db_session)
    run = await repo.create(
        ticket_id=ticket_id,
        project_id="proj-1",
        agent_id="software-architect",
        runner_mode="claude_code",
        context_snapshot={},
    )
    await db_session.commit()
    return run


async def test_append_creates_entry(db_session):
    """Appended entry is retrievable for the same ticket."""
    run = await _make_run(db_session)
    svc = WorkingMemoryService(db_session)
    entry = await svc.append(
        ticket_id="TICKET-WM-001",
        run_id=run.id,
        author_role_id="software-architect",
        entry_type="observation",
        content="Database schema looks solid.",
        tags=["schema"],
    )
    await db_session.commit()

    assert entry.id is not None
    assert entry.ticket_id == "TICKET-WM-001"
    assert entry.entry_type == "observation"
    assert "schema" in entry.tags


async def test_list_returns_entries_in_order(db_session):
    """Entries are returned in ascending created_at order."""
    run = await _make_run(db_session, ticket_id="TICKET-ORDER")
    svc = WorkingMemoryService(db_session)
    for i in range(3):
        await svc.append(
            ticket_id="TICKET-ORDER",
            run_id=run.id,
            author_role_id="software-architect",
            entry_type="observation",
            content=f"Entry {i}",
        )
    await db_session.commit()

    entries = await svc.list_for_ticket("TICKET-ORDER")
    contents = [e.content for e in entries]
    assert contents == ["Entry 0", "Entry 1", "Entry 2"]


async def test_list_filters_by_entry_type(db_session):
    """entry_type filter restricts results correctly."""
    run = await _make_run(db_session, ticket_id="TICKET-FILTER")
    svc = WorkingMemoryService(db_session)
    await svc.append("TICKET-FILTER", run.id, "sa", "observation", "obs 1")
    await svc.append("TICKET-FILTER", run.id, "sa", "decision", "dec 1")
    await svc.append("TICKET-FILTER", run.id, "sa", "observation", "obs 2")
    await db_session.commit()

    decisions = await svc.list_for_ticket("TICKET-FILTER", entry_type="decision")
    assert len(decisions) == 1
    assert decisions[0].entry_type == "decision"


async def test_list_filters_by_author_role(db_session):
    """author_role_id filter restricts results to that author."""
    run = await _make_run(db_session, ticket_id="TICKET-AUTHOR")
    svc = WorkingMemoryService(db_session)
    await svc.append("TICKET-AUTHOR", run.id, "software-architect", "observation", "arch note")
    await svc.append("TICKET-AUTHOR", run.id, "security-architect", "observation", "sec note")
    await db_session.commit()

    arch_entries = await svc.list_for_ticket("TICKET-AUTHOR", author_role_id="software-architect")
    assert len(arch_entries) == 1
    assert arch_entries[0].author_role_id == "software-architect"


async def test_cross_ticket_isolation_raises_permission_error(db_session):
    """Reading with a run_id from a different ticket raises PermissionError."""
    run_a = await _make_run(db_session, ticket_id="TICKET-A")
    run_b = await _make_run(db_session, ticket_id="TICKET-B")

    svc = WorkingMemoryService(db_session)
    await svc.append("TICKET-A", run_a.id, "sa", "observation", "data for A")
    await db_session.commit()

    # run_b belongs to TICKET-B, but we ask for TICKET-A entries
    with pytest.raises(PermissionError):
        await svc.list_for_ticket("TICKET-A", requester_run_id=run_b.id)


async def test_cross_ticket_isolation_same_ticket_ok(db_session):
    """Reading with the correct run_id for that ticket succeeds."""
    run = await _make_run(db_session, ticket_id="TICKET-SAME")
    svc = WorkingMemoryService(db_session)
    await svc.append("TICKET-SAME", run.id, "sa", "observation", "valid entry")
    await db_session.commit()

    entries = await svc.list_for_ticket("TICKET-SAME", requester_run_id=run.id)
    assert len(entries) == 1


async def test_entries_from_different_tickets_are_isolated(db_session):
    """list_for_ticket only returns entries for the requested ticket."""
    run_a = await _make_run(db_session, ticket_id="TICKET-ISO-A")
    run_b = await _make_run(db_session, ticket_id="TICKET-ISO-B")
    svc = WorkingMemoryService(db_session)
    await svc.append("TICKET-ISO-A", run_a.id, "sa", "observation", "for A")
    await svc.append("TICKET-ISO-B", run_b.id, "sa", "observation", "for B")
    await db_session.commit()

    entries_a = await svc.list_for_ticket("TICKET-ISO-A")
    entries_b = await svc.list_for_ticket("TICKET-ISO-B")

    assert all(e.ticket_id == "TICKET-ISO-A" for e in entries_a)
    assert all(e.ticket_id == "TICKET-ISO-B" for e in entries_b)
    assert len(entries_a) == 1
    assert len(entries_b) == 1


async def test_content_exceeding_max_length_raises(db_session):
    """Content over 65 536 chars is rejected before DB write."""
    run = await _make_run(db_session, ticket_id="TICKET-TOOLONG")
    svc = WorkingMemoryService(db_session)
    with pytest.raises(ValueError, match="maximum length"):
        await svc.append(
            ticket_id="TICKET-TOOLONG",
            run_id=run.id,
            author_role_id="sa",
            entry_type="observation",
            content="x" * 65_537,
        )


async def test_cleanup_expired_deletes_old_entries(db_session):
    """cleanup_expired() removes entries whose expires_at is in the past."""
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import update as sa_update
    from src.models.models import WorkingMemoryEntry

    run = await _make_run(db_session, ticket_id="TICKET-EXPIRE")
    svc = WorkingMemoryService(db_session)
    entry = await svc.append(
        ticket_id="TICKET-EXPIRE",
        run_id=run.id,
        author_role_id="sa",
        entry_type="observation",
        content="will expire",
    )
    await db_session.commit()

    # Force expiry into the past
    await db_session.execute(
        sa_update(WorkingMemoryEntry)
        .where(WorkingMemoryEntry.id == entry.id)
        .values(expires_at=datetime.now(UTC) - timedelta(days=1))
    )
    await db_session.commit()

    deleted = await svc.cleanup_expired()
    await db_session.commit()

    assert deleted >= 1

    remaining = await svc.list_for_ticket("TICKET-EXPIRE")
    assert not any(e.id == entry.id for e in remaining)


async def test_cleanup_does_not_delete_fresh_entries(db_session):
    """cleanup_expired() leaves non-expired entries untouched."""
    run = await _make_run(db_session, ticket_id="TICKET-FRESH")
    svc = WorkingMemoryService(db_session)
    await svc.append(
        ticket_id="TICKET-FRESH",
        run_id=run.id,
        author_role_id="sa",
        entry_type="observation",
        content="still valid",
    )
    await db_session.commit()

    deleted = await svc.cleanup_expired()
    await db_session.commit()

    entries = await svc.list_for_ticket("TICKET-FRESH")
    assert deleted == 0
    assert len(entries) == 1
