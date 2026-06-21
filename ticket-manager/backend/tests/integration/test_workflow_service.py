from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import hash_password
from src.models.progress_update import ProgressUpdate
from src.models.project import Project
from src.models.ticket import Ticket, TicketStatus
from src.models.ticket_assignment import TicketAssignment
from src.models.ticket_event import TicketEvent
from src.models.user import User, UserRole
from src.services.transition_service import transition_ticket
from src.services.workflow_service import validate_transition


async def _setup_with_all_progress(session: AsyncSession) -> tuple[User, Ticket]:
    user = User(email=f"{uuid4()}@t.com", hashed_password=hash_password("pw"), role=UserRole.user)
    session.add(user)
    await session.flush()

    project = Project(name="P", slug=f"p-{uuid4()}", created_by=user.id)
    session.add(project)
    await session.flush()

    ticket = Ticket(project_id=project.id, title="T", created_by=user.id, status=TicketStatus.OPEN)
    session.add(ticket)
    await session.flush()

    assignment = TicketAssignment(ticket_id=ticket.id, user_id=user.id, assigned_by=user.id)
    progress = ProgressUpdate(ticket_id=ticket.id, user_id=user.id, content="Done")
    session.add_all([assignment, progress])
    await session.commit()
    return user, ticket


@pytest.mark.asyncio
async def test_transition_emits_status_changed_event(db_session: AsyncSession):
    user, ticket = await _setup_with_all_progress(db_session)

    await transition_ticket(db_session, ticket.id, TicketStatus.IN_PROGRESS, user)

    result = await db_session.execute(
        select(TicketEvent).where(
            TicketEvent.ticket_id == ticket.id,
            TicketEvent.event_type == "ticket.status_changed",
        )
    )
    event = result.scalar_one()
    assert event.prev_state["status"] == "OPEN"
    assert event.new_state["status"] == "IN_PROGRESS"


@pytest.mark.asyncio
async def test_blocked_transition_emits_transition_blocked_event(db_session: AsyncSession):
    user = User(email=f"{uuid4()}@t.com", hashed_password=hash_password("pw"), role=UserRole.user)
    assignee2 = User(
        email=f"{uuid4()}@t.com", hashed_password=hash_password("pw"), role=UserRole.user
    )
    db_session.add_all([user, assignee2])
    await db_session.flush()

    project = Project(name="P", slug=f"p-{uuid4()}", created_by=user.id)
    db_session.add(project)
    await db_session.flush()

    ticket = Ticket(project_id=project.id, title="T", created_by=user.id, status=TicketStatus.OPEN)
    db_session.add(ticket)
    await db_session.flush()

    a1 = TicketAssignment(ticket_id=ticket.id, user_id=user.id, assigned_by=user.id)
    a2 = TicketAssignment(ticket_id=ticket.id, user_id=assignee2.id, assigned_by=user.id)
    p1 = ProgressUpdate(ticket_id=ticket.id, user_id=user.id, content="Only me")
    db_session.add_all([a1, a2, p1])
    await db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        await transition_ticket(db_session, ticket.id, TicketStatus.IN_PROGRESS, user)
    assert exc_info.value.status_code == 422

    result = await db_session.execute(
        select(TicketEvent).where(
            TicketEvent.ticket_id == ticket.id,
            TicketEvent.event_type == "ticket.transition_blocked",
        )
    )
    assert result.scalar_one_or_none() is not None


@pytest.mark.asyncio
async def test_closed_is_terminal():
    with pytest.raises(HTTPException) as exc_info:
        validate_transition(TicketStatus.CLOSED, TicketStatus.OPEN)
    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_transaction_rollback_on_gate_failure(db_session: AsyncSession):
    from sqlalchemy import select

    user = User(email=f"{uuid4()}@t.com", hashed_password=hash_password("pw"), role=UserRole.user)
    db_session.add(user)
    await db_session.flush()

    project = Project(name="P", slug=f"p-{uuid4()}", created_by=user.id)
    db_session.add(project)
    await db_session.flush()

    ticket = Ticket(project_id=project.id, title="T", created_by=user.id, status=TicketStatus.OPEN)
    db_session.add(ticket)
    await db_session.flush()

    assignment = TicketAssignment(ticket_id=ticket.id, user_id=user.id, assigned_by=user.id)
    db_session.add(assignment)
    await db_session.commit()

    original_status = ticket.status

    try:
        await transition_ticket(db_session, ticket.id, TicketStatus.IN_PROGRESS, user)
    except HTTPException:
        pass

    result = await db_session.execute(select(Ticket).where(Ticket.id == ticket.id))
    refreshed = result.scalar_one()
    assert refreshed.status == original_status
