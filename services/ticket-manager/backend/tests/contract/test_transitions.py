from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import create_access_token, hash_password
from src.models.project import Project
from src.models.ticket import Ticket, TicketStatus
from src.models.ticket_assignment import TicketAssignment
from src.models.user import User, UserRole


async def _setup(session: AsyncSession) -> tuple[User, User, Ticket]:
    owner = User(email=f"{uuid4()}@t.com", hashed_password=hash_password("pw"), role=UserRole.user)
    assignee2 = User(
        email=f"{uuid4()}@t.com", hashed_password=hash_password("pw"), role=UserRole.user
    )
    session.add_all([owner, assignee2])
    await session.flush()

    project = Project(name="P", slug=f"p-{uuid4()}", created_by=owner.id)
    session.add(project)
    await session.flush()

    ticket = Ticket(project_id=project.id, title="T", created_by=owner.id, status=TicketStatus.OPEN)
    session.add(ticket)
    await session.flush()

    a1 = TicketAssignment(ticket_id=ticket.id, user_id=owner.id, assigned_by=owner.id)
    a2 = TicketAssignment(ticket_id=ticket.id, user_id=assignee2.id, assigned_by=owner.id)
    session.add_all([a1, a2])
    await session.commit()
    return owner, assignee2, ticket


def _h(u: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(str(u.id), u.role.value)}"}


@pytest.mark.asyncio
async def test_transition_success_without_progress_200(
    client: AsyncClient, db_session: AsyncSession
):
    """Assignee can transition without any progress update — progress gate removed (FR-010)."""
    owner, _, ticket = await _setup(db_session)

    resp = await client.post(
        f"/api/v1/tickets/{ticket.id}/transitions",
        json={"to_status": "IN_PROGRESS"},
        headers=_h(owner),
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "IN_PROGRESS"


@pytest.mark.asyncio
async def test_transition_success_200(client: AsyncClient, db_session: AsyncSession):
    owner, _, ticket = await _setup(db_session)

    resp = await client.post(
        f"/api/v1/tickets/{ticket.id}/transitions",
        json={"to_status": "IN_PROGRESS"},
        headers=_h(owner),
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "IN_PROGRESS"


@pytest.mark.asyncio
async def test_transition_invalid_409(client: AsyncClient, db_session: AsyncSession):
    owner, _, ticket = await _setup(db_session)

    resp = await client.post(
        f"/api/v1/tickets/{ticket.id}/transitions",
        json={"to_status": "DONE"},
        headers=_h(owner),
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_transition_403_non_assignee(client: AsyncClient, db_session: AsyncSession):
    owner, _, ticket = await _setup(db_session)
    outsider = User(
        email=f"{uuid4()}@t.com", hashed_password=hash_password("pw"), role=UserRole.user
    )
    db_session.add(outsider)
    await db_session.commit()

    resp = await client.post(
        f"/api/v1/tickets/{ticket.id}/transitions",
        json={"to_status": "IN_PROGRESS"},
        headers=_h(outsider),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_transition_403_admin_non_assignee(client: AsyncClient, db_session: AsyncSession):
    owner, _, ticket = await _setup(db_session)
    admin = User(
        email=f"{uuid4()}@t.com",
        hashed_password=hash_password("pw"),
        role=UserRole.administrator,
    )
    db_session.add(admin)
    await db_session.commit()

    resp = await client.post(
        f"/api/v1/tickets/{ticket.id}/transitions",
        json={"to_status": "IN_PROGRESS"},
        headers=_h(admin),
    )
    assert resp.status_code == 403
