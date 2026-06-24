"""Integration tests for audit_service — T038.

Tests run against a real PostgreSQL database.
Assumes migrations 015 and 016 have been applied (alembic upgrade head).
"""

from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import hash_password
from src.models.project import Project
from src.models.ticket import Ticket, TicketStatus
from src.models.user import User, UserRole

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _user(session: AsyncSession) -> User:
    u = User(
        email=f"{uuid4()}@test.com",
        hashed_password=hash_password("pw"),
        role=UserRole.user,
    )
    session.add(u)
    await session.flush()
    return u


async def _project(session: AsyncSession, owner: User) -> Project:
    p = Project(name="P", slug=f"p-{uuid4()}", created_by=owner.id)
    session.add(p)
    await session.flush()
    return p


async def _ticket(session: AsyncSession, project: Project, creator: User) -> Ticket:
    t = Ticket(
        project_id=project.id,
        title=f"Ticket {uuid4()}",
        created_by=creator.id,
        status=TicketStatus.OPEN,
    )
    session.add(t)
    await session.flush()
    return t


# ---------------------------------------------------------------------------
# T038-A: create_audit_event + get_audit_log round-trip
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_and_retrieve_audit_event_round_trip(db_session: AsyncSession):
    from src.schemas.orchestrator import AuditEventCreate
    from src.services.audit_service import create_audit_event, get_audit_log

    user = await _user(db_session)
    project = await _project(db_session, user)
    ticket = await _ticket(db_session, project, user)
    await db_session.commit()

    body = AuditEventCreate(
        event="ADVANCE",
        actor="orchestrator",
        from_state="triage",
        to_state="specification",
        details="Moved forward after review",
    )
    created = await create_audit_event(db_session, ticket.id, body)

    assert created.id is not None
    assert created.event == "ADVANCE"
    assert created.actor == "orchestrator"
    assert created.from_state == "triage"
    assert created.to_state == "specification"
    assert created.details == "Moved forward after review"
    assert created.ticket_id == ticket.id

    log = await get_audit_log(db_session, ticket.id)
    assert len(log.entries) == 1
    entry = log.entries[0]
    assert entry.id == created.id
    assert entry.event == "ADVANCE"
    assert entry.actor == "orchestrator"
    assert entry.from_state == "triage"
    assert entry.to_state == "specification"


@pytest.mark.asyncio
async def test_multiple_events_returned_in_chronological_order(db_session: AsyncSession):
    from src.schemas.orchestrator import AuditEventCreate
    from src.services.audit_service import create_audit_event, get_audit_log

    user = await _user(db_session)
    project = await _project(db_session, user)
    ticket = await _ticket(db_session, project, user)
    await db_session.commit()

    events = [
        AuditEventCreate(
            event="ADVANCE", actor="orchestrator", from_state="backlog", to_state="triage"
        ),
        AuditEventCreate(
            event="BLOCK",
            actor="orchestrator",
            from_state="triage",
            to_state="BLOCKED",
            details="Missing spec",
        ),
        AuditEventCreate(
            event="ADVANCE", actor="orchestrator", from_state="BLOCKED", to_state="triage"
        ),
    ]
    for body in events:
        await create_audit_event(db_session, ticket.id, body)
    await db_session.commit()

    log = await get_audit_log(db_session, ticket.id)

    assert len(log.entries) == 3
    timestamps = [e.timestamp for e in log.entries]
    assert timestamps == sorted(timestamps), "Events must be in ascending chronological order"
    assert log.entries[0].event == "ADVANCE"
    assert log.entries[1].event == "BLOCK"
    assert log.entries[2].event == "ADVANCE"


@pytest.mark.asyncio
async def test_get_audit_log_returns_empty_list_for_ticket_with_no_events(
    db_session: AsyncSession,
):
    from src.services.audit_service import get_audit_log

    user = await _user(db_session)
    project = await _project(db_session, user)
    ticket = await _ticket(db_session, project, user)
    await db_session.commit()

    log = await get_audit_log(db_session, ticket.id)

    assert log.entries == []


# ---------------------------------------------------------------------------
# T038-B: Error handling — ticket-not-found
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_audit_event_for_nonexistent_ticket_raises_404(db_session: AsyncSession):
    from src.schemas.orchestrator import AuditEventCreate
    from src.services.audit_service import create_audit_event

    body = AuditEventCreate(event="ADVANCE", actor="orchestrator")
    with pytest.raises(HTTPException) as exc_info:
        await create_audit_event(db_session, uuid4(), body)
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_get_audit_log_for_nonexistent_ticket_raises_404(db_session: AsyncSession):
    from src.services.audit_service import get_audit_log

    with pytest.raises(HTTPException) as exc_info:
        await get_audit_log(db_session, uuid4())
    assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# T038-C: Audit immutability — no update/delete service functions
# ---------------------------------------------------------------------------


def test_audit_service_exposes_no_update_or_delete():
    """Verify that audit_service does not expose mutation functions for audit events."""
    import src.services.audit_service as audit_svc

    public_functions = [f for f in dir(audit_svc) if not f.startswith("_")]
    mutation_names = [
        f
        for f in public_functions
        if any(verb in f for verb in ("update", "delete", "remove", "patch", "modify"))
    ]
    assert mutation_names == [], (
        f"audit_service must not expose mutation functions; found: {mutation_names}"
    )


# ---------------------------------------------------------------------------
# T038-D: Event fields — all optional fields stored correctly
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_audit_event_optional_fields_stored_correctly(db_session: AsyncSession):
    from src.schemas.orchestrator import AuditEventCreate
    from src.services.audit_service import create_audit_event, get_audit_log

    user = await _user(db_session)
    project = await _project(db_session, user)
    ticket = await _ticket(db_session, project, user)
    await db_session.commit()

    # ASSIGN event: no from/to state, with details
    body = AuditEventCreate(
        event="ASSIGN",
        actor="orchestrator",
        details="Assigned to agent-99",
    )
    created = await create_audit_event(db_session, ticket.id, body)

    assert created.from_state is None
    assert created.to_state is None
    assert created.details == "Assigned to agent-99"

    log = await get_audit_log(db_session, ticket.id)
    entry = log.entries[0]
    assert entry.from_state is None
    assert entry.to_state is None
