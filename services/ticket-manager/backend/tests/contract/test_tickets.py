from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import create_access_token, hash_password
from src.models.project import Project
from src.models.ticket import Ticket, TicketStatus
from src.models.user import User, UserRole


async def _create_user(session: AsyncSession, email: str, role: UserRole = UserRole.user) -> User:
    user = User(email=email, hashed_password=hash_password("password"), role=role)
    session.add(user)
    await session.flush()
    return user


async def _create_project(session: AsyncSession, creator: User) -> Project:
    project = Project(name="Test Project", slug=f"test-{uuid4()}", created_by=creator.id)
    session.add(project)
    await session.flush()
    return project


def _auth_headers(user: User) -> dict:
    token = create_access_token(str(user.id), user.role.value)
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_create_ticket_201(client: AsyncClient, db_session: AsyncSession):
    user = await _create_user(db_session, f"u-{uuid4()}@test.com")
    project = await _create_project(db_session, user)
    await db_session.commit()

    resp = await client.post(
        f"/api/v1/projects/{project.id}/tickets",
        json={"title": "Test ticket", "ticket_spec": "backend"},
        headers=_auth_headers(user),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "Test ticket"
    assert data["status"] == "OPEN"


@pytest.mark.asyncio
async def test_get_ticket_200(client: AsyncClient, db_session: AsyncSession):
    user = await _create_user(db_session, f"u-{uuid4()}@test.com")
    project = await _create_project(db_session, user)
    ticket = Ticket(
        project_id=project.id,
        title="Get me",
        created_by=user.id,
        status=TicketStatus.OPEN,
    )
    db_session.add(ticket)
    await db_session.commit()

    resp = await client.get(f"/api/v1/tickets/{ticket.id}", headers=_auth_headers(user))
    assert resp.status_code == 200
    assert resp.json()["id"] == str(ticket.id)


@pytest.mark.asyncio
async def test_update_ticket_200(client: AsyncClient, db_session: AsyncSession):
    user = await _create_user(db_session, f"u-{uuid4()}@test.com")
    project = await _create_project(db_session, user)
    ticket = Ticket(
        project_id=project.id, title="Old", created_by=user.id, status=TicketStatus.OPEN
    )
    db_session.add(ticket)
    await db_session.commit()

    resp = await client.patch(
        f"/api/v1/tickets/{ticket.id}",
        json={"title": "New title"},
        headers=_auth_headers(user),
    )
    assert resp.status_code == 200
    assert resp.json()["title"] == "New title"


@pytest.mark.asyncio
async def test_delete_ticket_204(client: AsyncClient, db_session: AsyncSession):
    user = await _create_user(db_session, f"u-{uuid4()}@test.com")
    project = await _create_project(db_session, user)
    ticket = Ticket(
        project_id=project.id, title="Delete me", created_by=user.id, status=TicketStatus.OPEN
    )
    db_session.add(ticket)
    await db_session.commit()

    resp = await client.delete(f"/api/v1/tickets/{ticket.id}", headers=_auth_headers(user))
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_delete_ticket_409_with_follow_ups(client: AsyncClient, db_session: AsyncSession):
    user = await _create_user(db_session, f"u-{uuid4()}@test.com")
    project = await _create_project(db_session, user)
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

    resp = await client.delete(f"/api/v1/tickets/{parent.id}", headers=_auth_headers(user))
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_get_deleted_ticket_404(client: AsyncClient, db_session: AsyncSession):
    from datetime import UTC, datetime

    user = await _create_user(db_session, f"u-{uuid4()}@test.com")
    project = await _create_project(db_session, user)
    ticket = Ticket(
        project_id=project.id,
        title="Gone",
        created_by=user.id,
        status=TicketStatus.OPEN,
        deleted_at=datetime.now(UTC),
    )
    db_session.add(ticket)
    await db_session.commit()

    resp = await client.get(f"/api/v1/tickets/{ticket.id}", headers=_auth_headers(user))
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_ticket_403_non_creator(client: AsyncClient, db_session: AsyncSession):
    creator = await _create_user(db_session, f"creator-{uuid4()}@test.com")
    other = await _create_user(db_session, f"other-{uuid4()}@test.com")
    project = await _create_project(db_session, creator)
    ticket = Ticket(
        project_id=project.id, title="Mine", created_by=creator.id, status=TicketStatus.OPEN
    )
    db_session.add(ticket)
    await db_session.commit()

    resp = await client.patch(
        f"/api/v1/tickets/{ticket.id}",
        json={"title": "Steal"},
        headers=_auth_headers(other),
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# T028 — POST /api/v1/projects/{project_id}/tickets/{ticket_id}/tags/delta
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tag_delta_add_tag(client: AsyncClient, db_session: AsyncSession):
    user = await _create_user(db_session, f"u-{uuid4()}@test.com")
    project = await _create_project(db_session, user)
    ticket = Ticket(
        project_id=project.id, title="Tagged", created_by=user.id, status=TicketStatus.OPEN
    )
    db_session.add(ticket)
    await db_session.commit()

    resp = await client.post(
        f"/api/v1/projects/{project.id}/tickets/{ticket.id}/tags/delta",
        json={"add": ["needs-estimation"], "remove": []},
        headers=_auth_headers(user),
    )
    assert resp.status_code == 200
    tag_names = resp.json()["tags"]
    assert "needs-estimation" in tag_names


@pytest.mark.asyncio
async def test_tag_delta_remove_tag(client: AsyncClient, db_session: AsyncSession):
    from src.models.tag import Tag

    user = await _create_user(db_session, f"u-{uuid4()}@test.com")
    project = await _create_project(db_session, user)
    ticket = Ticket(
        project_id=project.id, title="Tagged", created_by=user.id, status=TicketStatus.OPEN
    )
    db_session.add(ticket)
    await db_session.flush()
    tag = Tag(name=f"remove-me-{uuid4()}")
    db_session.add(tag)
    await db_session.flush()
    await db_session.refresh(ticket, ["tags"])
    ticket.tags.append(tag)
    await db_session.commit()

    resp = await client.post(
        f"/api/v1/projects/{project.id}/tickets/{ticket.id}/tags/delta",
        json={"add": [], "remove": [tag.name]},
        headers=_auth_headers(user),
    )
    assert resp.status_code == 200
    tag_names = resp.json()["tags"]
    assert tag.name not in tag_names


@pytest.mark.asyncio
async def test_tag_delta_add_and_remove_in_same_call(client: AsyncClient, db_session: AsyncSession):
    from src.models.tag import Tag

    user = await _create_user(db_session, f"u-{uuid4()}@test.com")
    project = await _create_project(db_session, user)
    ticket = Ticket(
        project_id=project.id, title="Multi-tag", created_by=user.id, status=TicketStatus.OPEN
    )
    db_session.add(ticket)
    await db_session.flush()
    existing_tag = Tag(name=f"old-tag-{uuid4()}")
    db_session.add(existing_tag)
    await db_session.flush()
    await db_session.refresh(ticket, ["tags"])
    ticket.tags.append(existing_tag)
    await db_session.commit()

    resp = await client.post(
        f"/api/v1/projects/{project.id}/tickets/{ticket.id}/tags/delta",
        json={"add": ["new-tag"], "remove": [existing_tag.name]},
        headers=_auth_headers(user),
    )
    assert resp.status_code == 200
    tag_names = resp.json()["tags"]
    assert "new-tag" in tag_names
    assert existing_tag.name not in tag_names


@pytest.mark.asyncio
async def test_tag_delta_add_existing_tag_is_idempotent(
    client: AsyncClient, db_session: AsyncSession
):
    from src.models.tag import Tag

    user = await _create_user(db_session, f"u-{uuid4()}@test.com")
    project = await _create_project(db_session, user)
    ticket = Ticket(
        project_id=project.id, title="Idempotent", created_by=user.id, status=TicketStatus.OPEN
    )
    db_session.add(ticket)
    await db_session.flush()
    tag = Tag(name=f"already-there-{uuid4()}")
    db_session.add(tag)
    await db_session.flush()
    await db_session.refresh(ticket, ["tags"])
    ticket.tags.append(tag)
    await db_session.commit()

    # Add same tag twice
    for _ in range(2):
        resp = await client.post(
            f"/api/v1/projects/{project.id}/tickets/{ticket.id}/tags/delta",
            json={"add": [tag.name], "remove": []},
            headers=_auth_headers(user),
        )
        assert resp.status_code == 200

    tag_names = resp.json()["tags"]
    assert tag_names.count(tag.name) == 1


@pytest.mark.asyncio
async def test_tag_delta_remove_absent_tag_is_idempotent(
    client: AsyncClient, db_session: AsyncSession
):
    user = await _create_user(db_session, f"u-{uuid4()}@test.com")
    project = await _create_project(db_session, user)
    ticket = Ticket(
        project_id=project.id, title="No tags", created_by=user.id, status=TicketStatus.OPEN
    )
    db_session.add(ticket)
    await db_session.commit()

    resp = await client.post(
        f"/api/v1/projects/{project.id}/tickets/{ticket.id}/tags/delta",
        json={"add": [], "remove": ["nonexistent-tag"]},
        headers=_auth_headers(user),
    )
    assert resp.status_code == 200
    assert resp.json()["tags"] == []


@pytest.mark.asyncio
async def test_tag_delta_unknown_ticket_returns_404(client: AsyncClient, db_session: AsyncSession):
    user = await _create_user(db_session, f"u-{uuid4()}@test.com")
    project = await _create_project(db_session, user)
    await db_session.commit()

    resp = await client.post(
        f"/api/v1/projects/{project.id}/tickets/{uuid4()}/tags/delta",
        json={"add": ["tag"], "remove": []},
        headers=_auth_headers(user),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_tag_delta_non_project_owner_returns_403(
    client: AsyncClient, db_session: AsyncSession
):
    """Security: user who does not own the project cannot modify tags."""
    owner = await _create_user(db_session, f"owner-{uuid4()}@test.com")
    intruder = await _create_user(db_session, f"intruder-{uuid4()}@test.com")
    project = await _create_project(db_session, owner)
    ticket = Ticket(
        project_id=project.id, title="Protected", created_by=owner.id, status=TicketStatus.OPEN
    )
    db_session.add(ticket)
    await db_session.commit()

    resp = await client.post(
        f"/api/v1/projects/{project.id}/tickets/{ticket.id}/tags/delta",
        json={"add": ["injected-tag"], "remove": []},
        headers=_auth_headers(intruder),
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# T034 — GET /api/v1/projects/{project_id}/tickets?include_fsm=true
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_tickets_with_include_fsm_returns_fsm_fields(
    client: AsyncClient, db_session: AsyncSession
):
    user = await _create_user(db_session, f"u-{uuid4()}@test.com")
    project = await _create_project(db_session, user)
    db_session.add(
        Ticket(
            project_id=project.id, title="FSM ticket", created_by=user.id, status=TicketStatus.OPEN
        )
    )
    await db_session.commit()

    resp = await client.get(
        f"/api/v1/projects/{project.id}/tickets?include_fsm=true",
        headers=_auth_headers(user),
    )
    assert resp.status_code == 200
    tickets = resp.json()["tickets"]
    assert len(tickets) >= 1
    t = tickets[0]
    for field in (
        "fsm_status",
        "blocked_reason",
        "brainstorm_round",
        "assigned_agent",
        "override",
        "override_reason",
        "last_orchestrator_run",
        "orchestrator_errors",
    ):
        assert field in t, f"Missing FSM field in list response: {field}"


@pytest.mark.asyncio
async def test_list_tickets_without_include_fsm_no_regression(
    client: AsyncClient, db_session: AsyncSession
):
    """Default list response must not include FSM fields (backwards compatibility)."""
    user = await _create_user(db_session, f"u-{uuid4()}@test.com")
    project = await _create_project(db_session, user)
    db_session.add(
        Ticket(
            project_id=project.id,
            title="Normal ticket",
            created_by=user.id,
            status=TicketStatus.OPEN,
        )
    )
    await db_session.commit()

    resp = await client.get(
        f"/api/v1/projects/{project.id}/tickets",
        headers=_auth_headers(user),
    )
    assert resp.status_code == 200
    tickets = resp.json()["tickets"]
    assert len(tickets) >= 1
    t = tickets[0]
    for fsm_field in ("fsm_status", "brainstorm_round", "assigned_agent", "override"):
        assert fsm_field not in t, f"FSM field leaked into default list response: {fsm_field}"


@pytest.mark.asyncio
async def test_list_tickets_include_fsm_values_match_fsm_patch(
    client: AsyncClient, db_session: AsyncSession
):
    admin = await _create_user(db_session, f"admin-{uuid4()}@test.com", role=UserRole.administrator)
    project = await _create_project(db_session, admin)
    ticket = Ticket(
        project_id=project.id, title="Patched", created_by=admin.id, status=TicketStatus.OPEN
    )
    db_session.add(ticket)
    await db_session.commit()

    # Set FSM state via PATCH
    patch_resp = await client.patch(
        f"/api/v1/projects/{project.id}/tickets/{ticket.id}/fsm",
        json={"fsm_status": "code_review", "brainstorm_round": 5},
        headers=_auth_headers(admin),
    )
    assert patch_resp.status_code == 200

    list_resp = await client.get(
        f"/api/v1/projects/{project.id}/tickets?include_fsm=true",
        headers=_auth_headers(admin),
    )
    assert list_resp.status_code == 200
    tickets = list_resp.json()["tickets"]
    matching = [t for t in tickets if t["id"] == str(ticket.id)]
    assert len(matching) == 1
    assert matching[0]["fsm_status"] == "code_review"
    assert matching[0]["brainstorm_round"] == 5
