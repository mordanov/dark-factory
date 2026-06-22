from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import hash_password
from src.models.project import Project
from src.models.ticket import Ticket, TicketStatus
from src.models.ticket_event import TicketEvent
from src.models.user import User, UserRole
from src.schemas.ticket import TicketCreate, TicketUpdate
from src.services.ticket_service import (
    create_ticket,
    delete_ticket,
    update_ticket,
)


async def _user(s: AsyncSession) -> User:
    u = User(email=f"{uuid4()}@t.com", hashed_password=hash_password("pw"), role=UserRole.user)
    s.add(u)
    await s.flush()
    return u


async def _project(s: AsyncSession, owner: User) -> Project:
    p = Project(name="P", slug=f"p-{uuid4()}", created_by=owner.id)
    s.add(p)
    await s.flush()
    return p


@pytest.mark.asyncio
async def test_create_emits_ticket_created_event(db_session: AsyncSession):
    user = await _user(db_session)
    project = await _project(db_session, user)
    await db_session.commit()

    await create_ticket(
        db_session, project.id, TicketCreate(title="Test", ticket_spec="backend"), user
    )

    result = await db_session.execute(
        select(TicketEvent).where(TicketEvent.event_type == "ticket.created")
    )
    events = result.scalars().all()
    assert len(events) >= 1


@pytest.mark.asyncio
async def test_delete_blocked_by_follow_up(db_session: AsyncSession):
    from fastapi import HTTPException

    user = await _user(db_session)
    project = await _project(db_session, user)
    parent = Ticket(
        project_id=project.id, title="Parent", created_by=user.id, status=TicketStatus.OPEN
    )
    db_session.add(parent)
    await db_session.flush()
    child = Ticket(
        project_id=project.id,
        parent_ticket_id=parent.id,
        title="Child",
        created_by=user.id,
        status=TicketStatus.OPEN,
    )
    db_session.add(child)
    await db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        await delete_ticket(db_session, parent.id, user)
    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_delete_emits_ticket_deleted_event(db_session: AsyncSession):
    user = await _user(db_session)
    project = await _project(db_session, user)
    ticket = Ticket(
        project_id=project.id, title="Gone", created_by=user.id, status=TicketStatus.OPEN
    )
    db_session.add(ticket)
    await db_session.commit()

    await delete_ticket(db_session, ticket.id, user)

    result = await db_session.execute(
        select(TicketEvent).where(
            TicketEvent.ticket_id == ticket.id,
            TicketEvent.event_type == "ticket.deleted",
        )
    )
    assert result.scalar_one_or_none() is not None


@pytest.mark.asyncio
async def test_update_emits_correct_prev_new_state(db_session: AsyncSession):
    user = await _user(db_session)
    project = await _project(db_session, user)
    ticket = Ticket(
        project_id=project.id, title="Old title", created_by=user.id, status=TicketStatus.OPEN
    )
    db_session.add(ticket)
    await db_session.commit()

    await update_ticket(db_session, ticket.id, TicketUpdate(title="New title"), user)

    result = await db_session.execute(
        select(TicketEvent).where(
            TicketEvent.ticket_id == ticket.id,
            TicketEvent.event_type == "ticket.updated",
        )
    )
    event = result.scalar_one()
    assert event.prev_state["title"] == "Old title"
    assert event.new_state["title"] == "New title"
