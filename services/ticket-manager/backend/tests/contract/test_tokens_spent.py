from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import create_access_token, hash_password
from src.models.project import Project
from src.models.ticket import Ticket, TicketStatus
from src.models.ticket_assignment import TicketAssignment
from src.models.user import User, UserRole


def _h(u: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(str(u.id), u.role.value)}"}


async def _make_ticket_with_assignee(
    session: AsyncSession,
) -> tuple[User, Ticket]:
    user = User(email=f"{uuid4()}@t.com", hashed_password=hash_password("pw"), role=UserRole.user)
    session.add(user)
    await session.flush()

    project = Project(name="P", slug=f"p-{uuid4()}", created_by=user.id)
    session.add(project)
    await session.flush()

    ticket = Ticket(
        project_id=project.id,
        title="T",
        created_by=user.id,
        status=TicketStatus.IN_PROGRESS,
    )
    session.add(ticket)
    await session.flush()

    session.add(TicketAssignment(ticket_id=ticket.id, user_id=user.id, assigned_by=user.id))
    await session.commit()
    return user, ticket


@pytest.mark.asyncio
async def test_increment_tokens_spent_200(client: AsyncClient, db_session: AsyncSession):
    user, ticket = await _make_ticket_with_assignee(db_session)

    resp = await client.post(
        f"/api/v1/tickets/{ticket.id}/tokens-spent",
        json={"amount": 100},
        headers=_h(user),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["tokens_spent"] == 100
    assert data["amount_added"] == 100
    assert data["ticket_id"] == str(ticket.id)
    assert "event_id" in data


@pytest.mark.asyncio
async def test_increment_tokens_spent_accumulates(client: AsyncClient, db_session: AsyncSession):
    user, ticket = await _make_ticket_with_assignee(db_session)

    await client.post(
        f"/api/v1/tickets/{ticket.id}/tokens-spent",
        json={"amount": 50},
        headers=_h(user),
    )
    resp = await client.post(
        f"/api/v1/tickets/{ticket.id}/tokens-spent",
        json={"amount": 75},
        headers=_h(user),
    )
    assert resp.status_code == 200
    assert resp.json()["tokens_spent"] == 125


@pytest.mark.asyncio
async def test_increment_tokens_spent_zero_amount_422(
    client: AsyncClient, db_session: AsyncSession
):
    user, ticket = await _make_ticket_with_assignee(db_session)

    resp = await client.post(
        f"/api/v1/tickets/{ticket.id}/tokens-spent",
        json={"amount": 0},
        headers=_h(user),
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_increment_tokens_spent_negative_amount_422(
    client: AsyncClient, db_session: AsyncSession
):
    user, ticket = await _make_ticket_with_assignee(db_session)

    resp = await client.post(
        f"/api/v1/tickets/{ticket.id}/tokens-spent",
        json={"amount": -10},
        headers=_h(user),
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_increment_tokens_spent_non_assignee_403(
    client: AsyncClient, db_session: AsyncSession
):
    _, ticket = await _make_ticket_with_assignee(db_session)
    outsider = User(
        email=f"{uuid4()}@t.com", hashed_password=hash_password("pw"), role=UserRole.user
    )
    db_session.add(outsider)
    await db_session.commit()

    resp = await client.post(
        f"/api/v1/tickets/{ticket.id}/tokens-spent",
        json={"amount": 50},
        headers=_h(outsider),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_increment_tokens_spent_not_found_404(client: AsyncClient, db_session: AsyncSession):
    user = User(email=f"{uuid4()}@t.com", hashed_password=hash_password("pw"), role=UserRole.user)
    db_session.add(user)
    await db_session.commit()

    resp = await client.post(
        f"/api/v1/tickets/{uuid4()}/tokens-spent",
        json={"amount": 10},
        headers=_h(user),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_increment_tokens_spent_unauthenticated_401(
    client: AsyncClient, db_session: AsyncSession
):
    _, ticket = await _make_ticket_with_assignee(db_session)

    resp = await client.post(
        f"/api/v1/tickets/{ticket.id}/tokens-spent",
        json={"amount": 10},
    )
    assert resp.status_code == 401
