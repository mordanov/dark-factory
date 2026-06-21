from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import hash_password
from src.models.progress_update import ProgressUpdate
from src.models.project import Project
from src.models.ticket import Ticket, TicketStatus
from src.models.ticket_assignment import TicketAssignment
from src.models.ticket_event import TicketEvent
from src.models.user import User, UserRole
from src.services.assignment_service import unassign_user
from src.services.progress_service import submit_update


async def _setup(session: AsyncSession) -> tuple[User, User, Ticket]:
    owner = User(email=f"{uuid4()}@t.com", hashed_password=hash_password("pw"), role=UserRole.user)
    session.add(owner)
    await session.flush()

    project = Project(name="P", slug=f"p-{uuid4()}", created_by=owner.id)
    session.add(project)
    await session.flush()

    ticket = Ticket(project_id=project.id, title="T", created_by=owner.id, status=TicketStatus.OPEN)
    session.add(ticket)
    await session.flush()

    assignment = TicketAssignment(ticket_id=ticket.id, user_id=owner.id, assigned_by=owner.id)
    session.add(assignment)
    await session.commit()
    return owner, owner, ticket


@pytest.mark.asyncio
async def test_submit_update_first_time_prev_is_none(db_session: AsyncSession):
    user, _, ticket = await _setup(db_session)

    await submit_update(db_session, ticket.id, user, "First update")

    result = await db_session.execute(
        select(TicketEvent).where(
            TicketEvent.ticket_id == ticket.id,
            TicketEvent.event_type == "ticket.progress_updated",
        )
    )
    event = result.scalar_one()
    assert event.prev_state is None
    assert event.new_state["content"] == "First update"


@pytest.mark.asyncio
async def test_submit_update_emits_prev_content_on_update(db_session: AsyncSession):
    user, _, ticket = await _setup(db_session)

    await submit_update(db_session, ticket.id, user, "First")
    await submit_update(db_session, ticket.id, user, "Second")

    result = await db_session.execute(
        select(TicketEvent)
        .where(
            TicketEvent.ticket_id == ticket.id,
            TicketEvent.event_type == "ticket.progress_updated",
        )
        .order_by(TicketEvent.occurred_at.asc())
    )
    events = result.scalars().all()
    assert len(events) == 2
    assert events[1].prev_state["content"] == "First"
    assert events[1].new_state["content"] == "Second"


@pytest.mark.asyncio
async def test_unassign_leaves_progress_record(db_session: AsyncSession):
    owner = User(email=f"{uuid4()}@t.com", hashed_password=hash_password("pw"), role=UserRole.user)
    assignee = User(
        email=f"{uuid4()}@t.com", hashed_password=hash_password("pw"), role=UserRole.user
    )
    db_session.add_all([owner, assignee])
    await db_session.flush()

    project = Project(name="P", slug=f"p-{uuid4()}", created_by=owner.id)
    db_session.add(project)
    await db_session.flush()

    ticket = Ticket(project_id=project.id, title="T", created_by=owner.id, status=TicketStatus.OPEN)
    db_session.add(ticket)
    await db_session.flush()

    assignment = TicketAssignment(ticket_id=ticket.id, user_id=assignee.id, assigned_by=owner.id)
    progress = ProgressUpdate(ticket_id=ticket.id, user_id=assignee.id, content="Work done")
    db_session.add_all([assignment, progress])
    await db_session.commit()

    await unassign_user(db_session, ticket.id, assignee.id, owner)

    result = await db_session.execute(
        select(ProgressUpdate).where(
            ProgressUpdate.ticket_id == ticket.id,
            ProgressUpdate.user_id == assignee.id,
        )
    )
    assert result.scalar_one_or_none() is not None
