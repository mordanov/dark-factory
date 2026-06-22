from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import create_access_token, hash_password
from src.models.project import Project
from src.models.ticket import Ticket, TicketStatus
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
    await session.commit()
    return user, ticket


def _h(u: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(str(u.id), u.role.value)}"}


# ── Happy path ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_resource_increment_200(client: AsyncClient, db_session: AsyncSession):
    user, ticket = await _setup(db_session)

    resp = await client.post(
        f"/api/v1/tickets/{ticket.id}/resources",
        json={"time_spent_delta": 120, "tokens_consumed_delta": 500},
        headers=_h(user),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ticket_id"] == str(ticket.id)
    assert data["time_spent"] == 120
    assert data["tokens_consumed"] == 500
    assert "event_id" in data


@pytest.mark.asyncio
async def test_resource_increment_cumulative(client: AsyncClient, db_session: AsyncSession):
    user, ticket = await _setup(db_session)

    await client.post(
        f"/api/v1/tickets/{ticket.id}/resources",
        json={"time_spent_delta": 60, "tokens_consumed_delta": 200},
        headers=_h(user),
    )
    resp = await client.post(
        f"/api/v1/tickets/{ticket.id}/resources",
        json={"time_spent_delta": 60, "tokens_consumed_delta": 300},
        headers=_h(user),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["time_spent"] == 120
    assert data["tokens_consumed"] == 500


@pytest.mark.asyncio
async def test_resource_increment_time_only(client: AsyncClient, db_session: AsyncSession):
    user, ticket = await _setup(db_session)

    resp = await client.post(
        f"/api/v1/tickets/{ticket.id}/resources",
        json={"time_spent_delta": 90},
        headers=_h(user),
    )
    assert resp.status_code == 200
    assert resp.json()["time_spent"] == 90
    assert resp.json()["tokens_consumed"] == 0


@pytest.mark.asyncio
async def test_resource_increment_tokens_only(client: AsyncClient, db_session: AsyncSession):
    user, ticket = await _setup(db_session)

    resp = await client.post(
        f"/api/v1/tickets/{ticket.id}/resources",
        json={"tokens_consumed_delta": 1000},
        headers=_h(user),
    )
    assert resp.status_code == 200
    assert resp.json()["time_spent"] == 0
    assert resp.json()["tokens_consumed"] == 1000


@pytest.mark.asyncio
async def test_resource_increment_emits_event(client: AsyncClient, db_session: AsyncSession):
    user, ticket = await _setup(db_session)

    await client.post(
        f"/api/v1/tickets/{ticket.id}/resources",
        json={"time_spent_delta": 30, "tokens_consumed_delta": 100},
        headers=_h(user),
    )

    events_resp = await client.get(
        f"/api/v1/tickets/{ticket.id}/events",
        headers=_h(user),
    )
    assert events_resp.status_code == 200
    event_types = [e["event_type"] for e in events_resp.json()["items"]]
    assert "ticket.resources_incremented" in event_types


# ── Validation errors ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_resource_increment_400_both_zero(client: AsyncClient, db_session: AsyncSession):
    user, ticket = await _setup(db_session)

    resp = await client.post(
        f"/api/v1/tickets/{ticket.id}/resources",
        json={"time_spent_delta": 0, "tokens_consumed_delta": 0},
        headers=_h(user),
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_resource_increment_422_negative_time(client: AsyncClient, db_session: AsyncSession):
    user, ticket = await _setup(db_session)

    resp = await client.post(
        f"/api/v1/tickets/{ticket.id}/resources",
        json={"time_spent_delta": -10, "tokens_consumed_delta": 100},
        headers=_h(user),
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_resource_increment_422_negative_tokens(
    client: AsyncClient, db_session: AsyncSession
):
    user, ticket = await _setup(db_session)

    resp = await client.post(
        f"/api/v1/tickets/{ticket.id}/resources",
        json={"time_spent_delta": 60, "tokens_consumed_delta": -5},
        headers=_h(user),
    )
    assert resp.status_code == 422


# ── Auth / access errors ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_resource_increment_401_unauthenticated(
    client: AsyncClient, db_session: AsyncSession
):
    _, ticket = await _setup(db_session)

    resp = await client.post(
        f"/api/v1/tickets/{ticket.id}/resources",
        json={"time_spent_delta": 60, "tokens_consumed_delta": 100},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_resource_increment_404_missing_ticket(client: AsyncClient, db_session: AsyncSession):
    user, _ = await _setup(db_session)

    resp = await client.post(
        f"/api/v1/tickets/{uuid4()}/resources",
        json={"time_spent_delta": 60, "tokens_consumed_delta": 100},
        headers=_h(user),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_resource_increment_404_soft_deleted_ticket(
    client: AsyncClient, db_session: AsyncSession
):
    from datetime import UTC, datetime

    user, ticket = await _setup(db_session)
    ticket.deleted_at = datetime.now(UTC)
    await db_session.commit()

    resp = await client.post(
        f"/api/v1/tickets/{ticket.id}/resources",
        json={"time_spent_delta": 60, "tokens_consumed_delta": 100},
        headers=_h(user),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_resource_increment_any_authenticated_user(
    client: AsyncClient, db_session: AsyncSession
):
    """Any authenticated user can increment — no assignment check required."""
    _, ticket = await _setup(db_session)
    outsider = User(
        email=f"{uuid4()}@t.com", hashed_password=hash_password("pw"), role=UserRole.user
    )
    db_session.add(outsider)
    await db_session.commit()

    resp = await client.post(
        f"/api/v1/tickets/{ticket.id}/resources",
        json={"time_spent_delta": 15, "tokens_consumed_delta": 50},
        headers=_h(outsider),
    )
    assert resp.status_code == 200
