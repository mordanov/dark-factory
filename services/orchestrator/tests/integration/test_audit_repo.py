"""Integration tests — AuditRepository."""

import pytest
from src.repositories.audit_repo import AuditRepository


@pytest.mark.asyncio
async def test_append_and_list(db):
    repo = AuditRepository(db)
    await repo.append(
        ticket_id="tkt-audit-1",
        project_id="p-1",
        action="ADVANCE",
        from_state="triage",
        to_state="specification",
        assigned_agent="project_manager",
        details="Advanced to specification",
    )
    await repo.append(
        ticket_id="tkt-audit-1",
        project_id="p-1",
        action="BLOCK",
        from_state="specification",
        to_state=None,
        blocked_reason="Gate failed",
        details="Blocked at specification",
    )

    entries, total = await repo.list_for_ticket("tkt-audit-1")
    assert total == 2
    assert entries[0].action == "ADVANCE"
    assert entries[1].action == "BLOCK"
    assert entries[1].blocked_reason == "Gate failed"


@pytest.mark.asyncio
async def test_list_different_tickets_isolated(db):
    repo = AuditRepository(db)
    await repo.append(ticket_id="tkt-a", project_id="p-1", action="WAIT", details="d")
    await repo.append(ticket_id="tkt-b", project_id="p-1", action="ADVANCE", details="d")

    entries_a, total_a = await repo.list_for_ticket("tkt-a")
    entries_b, total_b = await repo.list_for_ticket("tkt-b")

    assert all(e.ticket_id == "tkt-a" for e in entries_a)
    assert all(e.ticket_id == "tkt-b" for e in entries_b)


@pytest.mark.asyncio
async def test_override_logged_flag(db):
    repo = AuditRepository(db)
    await repo.append(
        ticket_id="tkt-override",
        project_id="p-1",
        action="OVERRIDE_ACCEPTED",
        override_logged=True,
        details="Human override applied",
    )
    entries, _ = await repo.list_for_ticket("tkt-override")
    assert entries[0].override_logged is True
