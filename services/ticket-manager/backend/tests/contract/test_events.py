from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import create_access_token, hash_password
from src.models.project import Project
from src.models.ticket import Ticket, TicketStatus
from src.models.ticket_event import TicketEvent
from src.models.user import User, UserRole


async def _setup(session: AsyncSession) -> tuple[User, Ticket]:
    user = User(email=f"{uuid4()}@t.com", hashed_password=hash_password("pw"), role=UserRole.user)
    session.add(user)
    await session.flush()

    project = Project(name="P", slug=f"p-{uuid4()}", created_by=user.id)
    session.add(project)
    await session.flush()

    ticket = Ticket(project_id=project.id, title="T", created_by=user.id, status=TicketStatus.OPEN)
    session.add(ticket)
    await session.flush()

    for event_type in ["ticket.created", "ticket.updated"]:
        e = TicketEvent(
            ticket_id=ticket.id,
            event_type=event_type,
            actor_id=user.id,
            actor_role=user.role,
        )
        session.add(e)

    await session.commit()
    return user, ticket


def _h(u: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(str(u.id), u.role.value)}"}


@pytest.mark.asyncio
async def test_list_events_chronological(client: AsyncClient, db_session: AsyncSession):
    user, ticket = await _setup(db_session)

    resp = await client.get(f"/api/v1/tickets/{ticket.id}/events", headers=_h(user))
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) >= 2
    times = [i["occurred_at"] for i in items]
    assert times == sorted(times)


@pytest.mark.asyncio
async def test_event_has_actor_info(client: AsyncClient, db_session: AsyncSession):
    user, ticket = await _setup(db_session)

    resp = await client.get(f"/api/v1/tickets/{ticket.id}/events", headers=_h(user))
    items = resp.json()["items"]
    for item in items:
        assert "actor" in item
        assert "id" in item["actor"]
        assert "email" in item["actor"]
        assert "role" in item["actor"]
        assert "occurred_at" in item


@pytest.mark.asyncio
async def test_events_pagination(client: AsyncClient, db_session: AsyncSession):
    user, ticket = await _setup(db_session)

    resp = await client.get(
        f"/api/v1/tickets/{ticket.id}/events?page=1&page_size=1",
        headers=_h(user),
    )
    assert resp.status_code == 200
    assert len(resp.json()["items"]) == 1
