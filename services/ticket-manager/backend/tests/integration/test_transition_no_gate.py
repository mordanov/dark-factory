from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import hash_password
from src.models.project import Project
from src.models.ticket import Ticket, TicketStatus
from src.models.ticket_assignment import TicketAssignment
from src.models.user import User, UserRole
from src.services import transition_service


async def _make_assigned_ticket(session: AsyncSession) -> tuple[User, Ticket]:
    user = User(email=f"{uuid4()}@t.com", hashed_password=hash_password("pw"), role=UserRole.user)
    session.add(user)
    await session.flush()

    project = Project(name="P", slug=f"p-{uuid4()}", created_by=user.id)
    session.add(project)
    await session.flush()

    ticket = Ticket(
        project_id=project.id, title="T", created_by=user.id, status=TicketStatus.OPEN
    )
    session.add(ticket)
    await session.flush()

    assignment = TicketAssignment(ticket_id=ticket.id, user_id=user.id, assigned_by=user.id)
    session.add(assignment)
    await session.commit()
    return user, ticket


@pytest.mark.asyncio
async def test_transition_succeeds_without_progress_update(db_session: AsyncSession):
    user, ticket = await _make_assigned_ticket(db_session)

    result = await transition_service.transition_ticket(
        db_session, ticket.id, TicketStatus.IN_PROGRESS, user
    )
    assert result.status == TicketStatus.IN_PROGRESS.value


@pytest.mark.asyncio
async def test_transition_rejects_non_assignee(db_session: AsyncSession):
    _, ticket = await _make_assigned_ticket(db_session)
    outsider = User(
        email=f"{uuid4()}@t.com", hashed_password=hash_password("pw"), role=UserRole.user
    )
    db_session.add(outsider)
    await db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        await transition_service.transition_ticket(
            db_session, ticket.id, TicketStatus.IN_PROGRESS, outsider
        )
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_any_assignee_can_transition(db_session: AsyncSession):
    user1 = User(email=f"{uuid4()}@t.com", hashed_password=hash_password("pw"), role=UserRole.user)
    user2 = User(email=f"{uuid4()}@t.com", hashed_password=hash_password("pw"), role=UserRole.user)
    session = db_session
    session.add_all([user1, user2])
    await session.flush()

    project = Project(name="P", slug=f"p-{uuid4()}", created_by=user1.id)
    session.add(project)
    await session.flush()

    ticket = Ticket(
        project_id=project.id, title="T", created_by=user1.id, status=TicketStatus.OPEN
    )
    session.add(ticket)
    await session.flush()

    session.add_all([
        TicketAssignment(ticket_id=ticket.id, user_id=user1.id, assigned_by=user1.id),
        TicketAssignment(ticket_id=ticket.id, user_id=user2.id, assigned_by=user1.id),
    ])
    await session.commit()

    result = await transition_service.transition_ticket(
        session, ticket.id, TicketStatus.IN_PROGRESS, user2
    )
    assert result.status == TicketStatus.IN_PROGRESS.value
