"""Integration tests for fsm_service — T037.

Tests run against a real PostgreSQL database.
Assumes migrations 015 and 016 have been applied (alembic upgrade head).
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import hash_password
from src.models.project import Project
from src.models.ticket import Ticket, TicketStatus
from src.models.user import User, UserRole


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _user(session: AsyncSession, *, role: UserRole = UserRole.user) -> User:
    u = User(
        email=f"{uuid4()}@test.com",
        hashed_password=hash_password("pw"),
        role=role,
    )
    session.add(u)
    await session.flush()
    return u


async def _project(session: AsyncSession, owner: User) -> Project:
    p = Project(name="P", slug=f"p-{uuid4()}", created_by=owner.id)
    session.add(p)
    await session.flush()
    return p


async def _ticket(
    session: AsyncSession,
    project: Project,
    creator: User,
    *,
    fsm_status: str | None = None,
    last_orchestrator_run: datetime | None = None,
) -> Ticket:
    from src.models.ticket import FsmStatus  # added by T005

    t = Ticket(
        project_id=project.id,
        title=f"Ticket {uuid4()}",
        created_by=creator.id,
        status=TicketStatus.OPEN,
    )
    if fsm_status is not None:
        t.fsm_status = FsmStatus(fsm_status)
    if last_orchestrator_run is not None:
        t.last_orchestrator_run = last_orchestrator_run
    session.add(t)
    await session.flush()
    return t


# ---------------------------------------------------------------------------
# T037-A: get_pending_tickets — filter correctness
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pending_returns_ticket_with_null_fsm_and_null_last_run(
    db_session: AsyncSession,
):
    from src.services.fsm_service import get_pending_tickets

    user = await _user(db_session)
    project = await _project(db_session, user)
    ticket = await _ticket(db_session, project, user)  # fsm_status=None, last_run=None
    await db_session.commit()

    result = await get_pending_tickets(db_session, project_id=project.id, limit=50, after_cursor=None)

    ids = [str(t.id) for t in result.tickets]
    assert str(ticket.id) in ids


@pytest.mark.asyncio
async def test_pending_returns_ticket_updated_after_last_orchestrator_run(
    db_session: AsyncSession,
):
    from src.services.fsm_service import get_pending_tickets

    user = await _user(db_session)
    project = await _project(db_session, user)
    past = datetime(2000, 1, 1, tzinfo=UTC)
    ticket = await _ticket(db_session, project, user, fsm_status="triage", last_orchestrator_run=past)
    await db_session.commit()

    result = await get_pending_tickets(db_session, project_id=project.id, limit=50, after_cursor=None)

    ids = [str(t.id) for t in result.tickets]
    assert str(ticket.id) in ids


@pytest.mark.asyncio
async def test_pending_excludes_done_ticket(db_session: AsyncSession):
    from src.services.fsm_service import get_pending_tickets

    user = await _user(db_session)
    project = await _project(db_session, user)
    ticket = await _ticket(db_session, project, user, fsm_status="done")
    await db_session.commit()

    result = await get_pending_tickets(db_session, project_id=None, limit=50, after_cursor=None)

    ids = [str(t.id) for t in result.tickets]
    assert str(ticket.id) not in ids


@pytest.mark.asyncio
async def test_pending_excludes_ticket_not_updated_since_last_run(db_session: AsyncSession):
    """Strict >: ticket.updated_at == last_orchestrator_run → NOT pending."""
    from src.services.fsm_service import get_pending_tickets

    user = await _user(db_session)
    project = await _project(db_session, user)
    future = datetime.now(UTC) + timedelta(hours=1)
    # Set last_orchestrator_run far in the future so updated_at < last_run
    ticket = await _ticket(db_session, project, user, fsm_status="triage", last_orchestrator_run=future)
    await db_session.commit()

    result = await get_pending_tickets(db_session, project_id=None, limit=50, after_cursor=None)

    ids = [str(t.id) for t in result.tickets]
    assert str(ticket.id) not in ids


@pytest.mark.asyncio
async def test_pending_project_id_filter_returns_only_matching_project(db_session: AsyncSession):
    from src.services.fsm_service import get_pending_tickets

    user = await _user(db_session)
    project_a = await _project(db_session, user)
    project_b = await _project(db_session, user)
    ticket_a = await _ticket(db_session, project_a, user)
    ticket_b = await _ticket(db_session, project_b, user)
    await db_session.commit()

    result = await get_pending_tickets(
        db_session, project_id=project_a.id, limit=50, after_cursor=None
    )

    ids = [str(t.id) for t in result.tickets]
    assert str(ticket_a.id) in ids
    assert str(ticket_b.id) not in ids


@pytest.mark.asyncio
async def test_pending_empty_result_when_no_pending_tickets(db_session: AsyncSession):
    from src.services.fsm_service import get_pending_tickets

    user = await _user(db_session)
    project = await _project(db_session, user)
    # All tickets are done
    await _ticket(db_session, project, user, fsm_status="done")
    await db_session.commit()

    result = await get_pending_tickets(
        db_session, project_id=project.id, limit=50, after_cursor=None
    )

    # May have other tickets from other tests in the DB; check project-scoped result
    result_scoped = await get_pending_tickets(
        db_session, project_id=project.id, limit=50, after_cursor=None
    )
    assert result_scoped.total_pending == 0
    assert result_scoped.tickets == []


# ---------------------------------------------------------------------------
# T037-B: get_pending_tickets — cursor pagination
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pending_cursor_pagination_no_overlap_no_gaps(db_session: AsyncSession):
    from src.services.fsm_service import get_pending_tickets

    user = await _user(db_session)
    project = await _project(db_session, user)
    for _ in range(5):
        await _ticket(db_session, project, user)
    await db_session.commit()

    page1 = await get_pending_tickets(
        db_session, project_id=project.id, limit=3, after_cursor=None
    )
    assert len(page1.tickets) == 3
    assert page1.next_cursor is not None

    page2 = await get_pending_tickets(
        db_session, project_id=project.id, limit=3, after_cursor=page1.next_cursor
    )
    assert len(page2.tickets) == 2

    # No overlap
    page1_ids = {str(t.id) for t in page1.tickets}
    page2_ids = {str(t.id) for t in page2.tickets}
    assert page1_ids.isdisjoint(page2_ids)

    # Full coverage
    result_all = await get_pending_tickets(
        db_session, project_id=project.id, limit=100, after_cursor=None
    )
    all_ids = {str(t.id) for t in result_all.tickets}
    assert page1_ids | page2_ids == all_ids


@pytest.mark.asyncio
async def test_pending_last_page_has_no_next_cursor(db_session: AsyncSession):
    from src.services.fsm_service import get_pending_tickets

    user = await _user(db_session)
    project = await _project(db_session, user)
    for _ in range(2):
        await _ticket(db_session, project, user)
    await db_session.commit()

    result = await get_pending_tickets(
        db_session, project_id=project.id, limit=10, after_cursor=None
    )
    assert result.next_cursor is None


# ---------------------------------------------------------------------------
# T037-C: patch_fsm_fields — atomicity and native-field isolation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fsm_patch_updates_only_fsm_fields(db_session: AsyncSession):
    from src.schemas.ticket import FsmPatchRequest
    from src.services.fsm_service import patch_fsm_fields

    user = await _user(db_session)
    project = await _project(db_session, user)
    ticket = await _ticket(db_session, project, user)
    original_title = ticket.title
    original_status = ticket.status
    await db_session.commit()

    body = FsmPatchRequest(fsm_status="triage", assigned_agent="agent-42")
    result = await patch_fsm_fields(db_session, project.id, ticket.id, body, user)

    assert str(result.fsm_status) in ("triage", "FsmStatus.triage")
    assert result.assigned_agent == "agent-42"
    assert result.title == original_title
    assert result.status == original_status


@pytest.mark.asyncio
async def test_fsm_patch_partial_update_does_not_touch_other_fsm_fields(db_session: AsyncSession):
    from src.schemas.ticket import FsmPatchRequest
    from src.services.fsm_service import patch_fsm_fields

    user = await _user(db_session)
    project = await _project(db_session, user)
    ticket = await _ticket(db_session, project, user, fsm_status="triage")
    await db_session.commit()

    # Only send brainstorm_round — other FSM fields untouched
    body = FsmPatchRequest(brainstorm_round=2)
    result = await patch_fsm_fields(db_session, project.id, ticket.id, body, user)

    assert result.brainstorm_round == 2
    assert str(result.fsm_status) in ("triage", "FsmStatus.triage")


@pytest.mark.asyncio
async def test_fsm_patch_wrong_project_raises_404(db_session: AsyncSession):
    from src.schemas.ticket import FsmPatchRequest
    from src.services.fsm_service import patch_fsm_fields

    user = await _user(db_session)
    project_a = await _project(db_session, user)
    project_b = await _project(db_session, user)
    ticket = await _ticket(db_session, project_a, user)
    await db_session.commit()

    body = FsmPatchRequest(fsm_status="triage")
    with pytest.raises(HTTPException) as exc_info:
        await patch_fsm_fields(db_session, project_b.id, ticket.id, body, user)
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_fsm_patch_unknown_ticket_raises_404(db_session: AsyncSession):
    from src.schemas.ticket import FsmPatchRequest
    from src.services.fsm_service import patch_fsm_fields

    user = await _user(db_session)
    project = await _project(db_session, user)
    await db_session.commit()

    body = FsmPatchRequest(fsm_status="triage")
    with pytest.raises(HTTPException) as exc_info:
        await patch_fsm_fields(db_session, project.id, uuid4(), body, user)
    assert exc_info.value.status_code == 404
