from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import hash_password
from src.models.project import Project
from src.models.ticket import Ticket, TicketStatus
from src.models.ticket_assignment import TicketAssignment
from src.models.ticket_event import TicketEvent
from src.models.user import User, UserRole
from src.services import tokens_spent_service


async def _setup(session: AsyncSession) -> tuple[User, Ticket]:
    user = User(email=f"{uuid4()}@t.com", hashed_password=hash_password("pw"), role=UserRole.user)
    session.add(user)
    await session.flush()

    project = Project(name="P", slug=f"p-{uuid4()}", created_by=user.id)
    session.add(project)
    await session.flush()

    ticket = Ticket(
        project_id=project.id, title="T", created_by=user.id, status=TicketStatus.IN_PROGRESS
    )
    session.add(ticket)
    await session.flush()

    session.add(TicketAssignment(ticket_id=ticket.id, user_id=user.id, assigned_by=user.id))
    await session.commit()
    return user, ticket


@pytest.mark.asyncio
async def test_increment_returns_correct_total(db_session: AsyncSession):
    user, ticket = await _setup(db_session)

    result = await tokens_spent_service.increment_tokens_spent(db_session, ticket.id, 200, user)
    assert result.tokens_spent == 200
    assert result.amount_added == 200


@pytest.mark.asyncio
async def test_multiple_increments_accumulate(db_session: AsyncSession):
    user, ticket = await _setup(db_session)

    await tokens_spent_service.increment_tokens_spent(db_session, ticket.id, 100, user)
    result = await tokens_spent_service.increment_tokens_spent(db_session, ticket.id, 50, user)
    assert result.tokens_spent == 150


@pytest.mark.asyncio
async def test_increment_emits_event(db_session: AsyncSession):
    user, ticket = await _setup(db_session)

    result = await tokens_spent_service.increment_tokens_spent(db_session, ticket.id, 300, user)

    events = await db_session.execute(
        select(TicketEvent).where(
            TicketEvent.ticket_id == ticket.id,
            TicketEvent.event_type == "ticket.tokens_spent_incremented",
        )
    )
    event = events.scalar_one()
    assert event.id == result.event_id
    assert event.new_state["tokens_spent"] == 300
    assert event.metadata_["amount_added"] == 300


@pytest.mark.asyncio
async def test_increment_non_assignee_raises_403(db_session: AsyncSession):
    _, ticket = await _setup(db_session)
    outsider = User(
        email=f"{uuid4()}@t.com", hashed_password=hash_password("pw"), role=UserRole.user
    )
    db_session.add(outsider)
    await db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        await tokens_spent_service.increment_tokens_spent(db_session, ticket.id, 10, outsider)
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_increment_missing_ticket_raises_404(db_session: AsyncSession):
    user = User(email=f"{uuid4()}@t.com", hashed_password=hash_password("pw"), role=UserRole.user)
    db_session.add(user)
    await db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        await tokens_spent_service.increment_tokens_spent(db_session, uuid4(), 10, user)
    assert exc_info.value.status_code == 404
