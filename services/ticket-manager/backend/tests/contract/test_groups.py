from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import create_access_token, hash_password
from src.models.project import Project
from src.models.project_group import ProjectGroup
from src.models.user import User, UserRole


def _h(u: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(str(u.id), u.role.value)}"}


async def _make_user(session: AsyncSession) -> User:
    u = User(email=f"{uuid4()}@t.com", hashed_password=hash_password("pw"), role=UserRole.user)
    session.add(u)
    await session.flush()
    return u


@pytest.mark.asyncio
async def test_create_group_201(client: AsyncClient, db_session: AsyncSession):
    user = await _make_user(db_session)
    await db_session.commit()

    resp = await client.post(
        "/api/v1/groups",
        json={"identifier": "TEAM1", "name": "Team One"},
        headers=_h(user),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["identifier"] == "TEAM1"
    assert data["is_system"] is False
    assert data["project_count"] == 0


@pytest.mark.asyncio
async def test_create_group_normalizes_lowercase(client: AsyncClient, db_session: AsyncSession):
    user = await _make_user(db_session)
    await db_session.commit()

    resp = await client.post(
        "/api/v1/groups",
        json={"identifier": "teama", "name": "Team A"},
        headers=_h(user),
    )
    assert resp.status_code == 201
    assert resp.json()["identifier"] == "TEAMA"


@pytest.mark.asyncio
async def test_create_group_duplicate_409(client: AsyncClient, db_session: AsyncSession):
    user = await _make_user(db_session)
    group = ProjectGroup(identifier="DUPID", name="Dup")
    db_session.add(group)
    await db_session.commit()

    resp = await client.post(
        "/api/v1/groups",
        json={"identifier": "DUPID", "name": "Another"},
        headers=_h(user),
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_create_group_invalid_identifier_422(client: AsyncClient, db_session: AsyncSession):
    user = await _make_user(db_session)
    await db_session.commit()

    # Too short
    resp = await client.post(
        "/api/v1/groups",
        json={"identifier": "AB", "name": "Short"},
        headers=_h(user),
    )
    assert resp.status_code == 422

    # Contains special chars
    resp2 = await client.post(
        "/api/v1/groups",
        json={"identifier": "TEAM-1!", "name": "Bad"},
        headers=_h(user),
    )
    assert resp2.status_code == 422


@pytest.mark.asyncio
async def test_list_groups_includes_default(client: AsyncClient, db_session: AsyncSession):
    user = await _make_user(db_session)
    await db_session.commit()

    resp = await client.get("/api/v1/groups", headers=_h(user))
    assert resp.status_code == 200
    data = resp.json()
    identifiers = [g["identifier"] for g in data["items"]]
    assert "DEFAULT" in identifiers


@pytest.mark.asyncio
async def test_get_group_200(client: AsyncClient, db_session: AsyncSession):
    user = await _make_user(db_session)
    group = ProjectGroup(identifier="GRPA1", name="Group A")
    db_session.add(group)
    await db_session.commit()

    resp = await client.get(f"/api/v1/groups/{group.id}", headers=_h(user))
    assert resp.status_code == 200
    assert resp.json()["identifier"] == "GRPA1"


@pytest.mark.asyncio
async def test_get_group_404(client: AsyncClient, db_session: AsyncSession):
    user = await _make_user(db_session)
    await db_session.commit()

    resp = await client.get(f"/api/v1/groups/{uuid4()}", headers=_h(user))
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_group_200(client: AsyncClient, db_session: AsyncSession):
    user = await _make_user(db_session)
    group = ProjectGroup(identifier="UPDT1", name="Before")
    db_session.add(group)
    await db_session.commit()

    resp = await client.patch(
        f"/api/v1/groups/{group.id}",
        json={"name": "After"},
        headers=_h(user),
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "After"


@pytest.mark.asyncio
async def test_delete_system_group_409(client: AsyncClient, db_session: AsyncSession):
    user = await _make_user(db_session)
    await db_session.commit()

    # Find DEFAULT group
    from sqlalchemy import select

    from src.models.project_group import ProjectGroup as PG

    result = await db_session.execute(select(PG).where(PG.identifier == "DEFAULT"))
    default = result.scalar_one()

    resp = await client.delete(f"/api/v1/groups/{default.id}", headers=_h(user))
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_delete_group_with_projects_409(client: AsyncClient, db_session: AsyncSession):
    user = await _make_user(db_session)
    group = ProjectGroup(identifier="USED1", name="Used")
    db_session.add(group)
    await db_session.flush()

    project = Project(name="P", slug=f"p-{uuid4()}", group_id=group.id, created_by=user.id)
    db_session.add(project)
    await db_session.commit()

    resp = await client.delete(f"/api/v1/groups/{group.id}", headers=_h(user))
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_delete_empty_group_204(client: AsyncClient, db_session: AsyncSession):
    user = await _make_user(db_session)
    group = ProjectGroup(identifier="EMPT1", name="Empty")
    db_session.add(group)
    await db_session.commit()

    resp = await client.delete(f"/api/v1/groups/{group.id}", headers=_h(user))
    assert resp.status_code == 204
