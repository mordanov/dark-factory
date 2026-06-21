from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import create_access_token, hash_password
from src.models.progress_update import ProgressUpdate
from src.models.project import Project
from src.models.ticket import Ticket, TicketStatus
from src.models.user import User, UserRole


async def _make_user(s: AsyncSession) -> User:
    u = User(email=f"{uuid4()}@t.com", hashed_password=hash_password("pw"), role=UserRole.user)
    s.add(u)
    await s.flush()
    return u


async def _make_project(s: AsyncSession, owner: User) -> Project:
    p = Project(name="P", slug=f"p-{uuid4()}", created_by=owner.id)
    s.add(p)
    await s.flush()
    return p


async def _make_ticket(s: AsyncSession, project: Project, owner: User) -> Ticket:
    t = Ticket(project_id=project.id, title="T", created_by=owner.id, status=TicketStatus.OPEN)
    s.add(t)
    await s.flush()
    return t


def _headers(u: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(str(u.id), u.role.value)}"}


@pytest.mark.asyncio
async def test_assign_201(client: AsyncClient, db_session: AsyncSession):
    owner = await _make_user(db_session)
    assignee = await _make_user(db_session)
    project = await _make_project(db_session, owner)
    ticket = await _make_ticket(db_session, project, owner)
    await db_session.commit()

    resp = await client.post(
        f"/api/v1/tickets/{ticket.id}/assignments",
        json={"user_id": str(assignee.id)},
        headers=_headers(owner),
    )
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_assign_duplicate_409(client: AsyncClient, db_session: AsyncSession):
    owner = await _make_user(db_session)
    assignee = await _make_user(db_session)
    project = await _make_project(db_session, owner)
    ticket = await _make_ticket(db_session, project, owner)
    await db_session.commit()

    headers = _headers(owner)
    await client.post(
        f"/api/v1/tickets/{ticket.id}/assignments",
        json={"user_id": str(assignee.id)},
        headers=headers,
    )
    resp = await client.post(
        f"/api/v1/tickets/{ticket.id}/assignments",
        json={"user_id": str(assignee.id)},
        headers=headers,
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_unassign_204(client: AsyncClient, db_session: AsyncSession):
    owner = await _make_user(db_session)
    assignee = await _make_user(db_session)
    project = await _make_project(db_session, owner)
    ticket = await _make_ticket(db_session, project, owner)
    await db_session.commit()

    headers = _headers(owner)
    await client.post(
        f"/api/v1/tickets/{ticket.id}/assignments",
        json={"user_id": str(assignee.id)},
        headers=headers,
    )
    resp = await client.delete(
        f"/api/v1/tickets/{ticket.id}/assignments/{assignee.id}",
        headers=headers,
    )
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_unassign_403_unauthorized_user(client: AsyncClient, db_session: AsyncSession):
    owner = await _make_user(db_session)
    assignee = await _make_user(db_session)
    outsider = await _make_user(db_session)
    project = await _make_project(db_session, owner)
    ticket = await _make_ticket(db_session, project, owner)
    from src.models.ticket_assignment import TicketAssignment

    assignment = TicketAssignment(ticket_id=ticket.id, user_id=assignee.id, assigned_by=owner.id)
    db_session.add(assignment)
    await db_session.commit()

    resp = await client.delete(
        f"/api/v1/tickets/{ticket.id}/assignments/{assignee.id}",
        headers=_headers(outsider),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_unassign_preserves_progress(client: AsyncClient, db_session: AsyncSession):
    owner = await _make_user(db_session)
    assignee = await _make_user(db_session)
    project = await _make_project(db_session, owner)
    ticket = await _make_ticket(db_session, project, owner)
    progress = ProgressUpdate(ticket_id=ticket.id, user_id=assignee.id, content="Done something")
    db_session.add(progress)
    await db_session.commit()

    from src.models.ticket_assignment import TicketAssignment

    assignment = TicketAssignment(ticket_id=ticket.id, user_id=assignee.id, assigned_by=owner.id)
    db_session.add(assignment)
    await db_session.commit()

    await client.delete(
        f"/api/v1/tickets/{ticket.id}/assignments/{assignee.id}",
        headers=_headers(owner),
    )

    from sqlalchemy import select

    result = await db_session.execute(
        select(ProgressUpdate).where(
            ProgressUpdate.ticket_id == ticket.id,
            ProgressUpdate.user_id == assignee.id,
        )
    )
    assert result.scalar_one_or_none() is not None
