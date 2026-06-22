"""Contract tests for orchestrator endpoints — T011, T014, T017, T022, T025, T031.

Tests cover:
  T011 — GET /api/v1/orchestrator/pending (US1)
  T014 — PATCH /api/v1/projects/{id}/tickets/{id}/fsm (US2)
  T017 — POST/GET /api/v1/tickets/{id}/audit (US3)
  T022 — POST /api/v1/projects/{id}/tickets/{id}/override (US4)
  T025 — POST /api/v1/tickets/batch-fsm-status (US5)
  T031 — GET /api/v1/projects/{id}/tickets/{id}/full (US7)

Security findings from security-architect incorporated:
  - batch-fsm-status must not leak tickets from inaccessible projects
  - POST /audit restricted to service-account-or-admin
  - tags/delta needs project-level write check (covered in test_tickets.py)
"""

from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.security import create_access_token, hash_password
from src.models.project import Project
from src.models.ticket import Ticket, TicketStatus
from src.models.user import User, UserRole

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _user(
    session: AsyncSession,
    *,
    role: UserRole = UserRole.user,
    email: str | None = None,
) -> User:
    u = User(
        email=email or f"{uuid4()}@test.com",
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
    title: str | None = None,
    fsm_status: str | None = None,
) -> Ticket:
    t = Ticket(
        project_id=project.id,
        title=title or f"Ticket {uuid4()}",
        created_by=creator.id,
        status=TicketStatus.OPEN,
    )
    if fsm_status is not None:
        from src.models.ticket import FsmStatus

        t.fsm_status = FsmStatus(fsm_status)
    session.add(t)
    await session.flush()
    return t


def _auth(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(str(user.id), user.role.value)}"}


def _service_auth() -> dict:
    """Return auth header for the configured service account (or a skip marker)."""
    if not settings.ticket_manager_service_email:
        pytest.skip("TICKET_MANAGER_SERVICE_EMAIL not configured")
    # The service account user must exist in the DB — tests that call this must create it.
    return {}  # replaced per-test by creating the service user


# ---------------------------------------------------------------------------
# T011 — GET /api/v1/orchestrator/pending
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pending_returns_pending_tickets(client: AsyncClient, db_session: AsyncSession):
    user = await _user(db_session)
    project = await _project(db_session, user)
    ticket = await _ticket(db_session, project, user)  # fsm_status=None → pending
    await db_session.commit()

    resp = await client.get(
        f"/api/v1/orchestrator/pending?project_id={project.id}",
        headers=_auth(user),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "tickets" in data
    assert "total_pending" in data
    assert "next_cursor" in data
    ids = [t["id"] for t in data["tickets"]]
    assert str(ticket.id) in ids


@pytest.mark.asyncio
async def test_pending_excludes_done_tickets(client: AsyncClient, db_session: AsyncSession):
    user = await _user(db_session)
    project = await _project(db_session, user)
    done_ticket = await _ticket(db_session, project, user, fsm_status="done")
    await db_session.commit()

    resp = await client.get(
        f"/api/v1/orchestrator/pending?project_id={project.id}",
        headers=_auth(user),
    )
    assert resp.status_code == 200
    ids = [t["id"] for t in resp.json()["tickets"]]
    assert str(done_ticket.id) not in ids


@pytest.mark.asyncio
async def test_pending_project_id_filter(client: AsyncClient, db_session: AsyncSession):
    user = await _user(db_session)
    project_a = await _project(db_session, user)
    project_b = await _project(db_session, user)
    ticket_a = await _ticket(db_session, project_a, user)
    ticket_b = await _ticket(db_session, project_b, user)
    await db_session.commit()

    resp = await client.get(
        f"/api/v1/orchestrator/pending?project_id={project_a.id}",
        headers=_auth(user),
    )
    assert resp.status_code == 200
    ids = [t["id"] for t in resp.json()["tickets"]]
    assert str(ticket_a.id) in ids
    assert str(ticket_b.id) not in ids


@pytest.mark.asyncio
async def test_pending_limit_and_pagination(client: AsyncClient, db_session: AsyncSession):
    user = await _user(db_session)
    project = await _project(db_session, user)
    for _ in range(5):
        await _ticket(db_session, project, user)
    await db_session.commit()

    resp = await client.get(
        f"/api/v1/orchestrator/pending?project_id={project.id}&limit=3",
        headers=_auth(user),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["tickets"]) == 3
    assert data["next_cursor"] is not None


@pytest.mark.asyncio
async def test_pending_empty_result(client: AsyncClient, db_session: AsyncSession):
    user = await _user(db_session)
    project = await _project(db_session, user)
    await _ticket(db_session, project, user, fsm_status="done")
    await db_session.commit()

    resp = await client.get(
        f"/api/v1/orchestrator/pending?project_id={project.id}",
        headers=_auth(user),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_pending"] == 0
    assert data["tickets"] == []
    assert data["next_cursor"] is None


@pytest.mark.asyncio
async def test_pending_unauthenticated_returns_401(client: AsyncClient):
    resp = await client.get("/api/v1/orchestrator/pending")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_pending_non_service_account_returns_403_when_svc_configured(
    client: AsyncClient, db_session: AsyncSession
):
    """Security: when TICKET_MANAGER_SERVICE_EMAIL is set, non-service regular users must be blocked."""
    svc_email = "svc-pending-sec@test.com"
    original_svc = settings.ticket_manager_service_email
    settings.ticket_manager_service_email = svc_email

    regular_user = await _user(db_session)  # not svc, not admin
    await db_session.commit()

    try:
        resp = await client.get(
            "/api/v1/orchestrator/pending",
            headers=_auth(regular_user),
        )
        # Per security-architect finding: pending endpoint should be restricted to svc-or-admin
        assert resp.status_code == 403
    finally:
        settings.ticket_manager_service_email = original_svc


@pytest.mark.asyncio
async def test_pending_ticket_includes_required_fields(
    client: AsyncClient, db_session: AsyncSession
):
    user = await _user(db_session)
    project = await _project(db_session, user)
    await _ticket(db_session, project, user)
    await db_session.commit()

    resp = await client.get(
        f"/api/v1/orchestrator/pending?project_id={project.id}",
        headers=_auth(user),
    )
    assert resp.status_code == 200
    tickets = resp.json()["tickets"]
    assert len(tickets) >= 1
    t = tickets[0]
    for field in ("id", "project_id", "title", "status", "created_at", "updated_at"):
        assert field in t, f"Missing field: {field}"


# ---------------------------------------------------------------------------
# T014 — PATCH /api/v1/projects/{project_id}/tickets/{ticket_id}/fsm
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fsm_patch_service_account_updates_fsm_fields(
    client: AsyncClient, db_session: AsyncSession
):
    svc_email = f"svc-{uuid4()}@test.com"
    original_svc = settings.ticket_manager_service_email
    settings.ticket_manager_service_email = svc_email

    svc_user = await _user(db_session, email=svc_email)
    user = await _user(db_session)
    project = await _project(db_session, user)
    ticket = await _ticket(db_session, project, user, title="Original title")
    await db_session.commit()

    try:
        resp = await client.patch(
            f"/api/v1/projects/{project.id}/tickets/{ticket.id}/fsm",
            json={"fsm_status": "triage", "assigned_agent": "agent-42"},
            headers=_auth(svc_user),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["fsm_status"] == "triage"
        assert data["assigned_agent"] == "agent-42"
        # Native fields unchanged
        assert data["title"] == "Original title"
        assert data["status"] == "OPEN"
    finally:
        settings.ticket_manager_service_email = original_svc


@pytest.mark.asyncio
async def test_fsm_patch_admin_allowed(client: AsyncClient, db_session: AsyncSession):
    admin = await _user(db_session, role=UserRole.administrator)
    project = await _project(db_session, admin)
    ticket = await _ticket(db_session, project, admin)
    await db_session.commit()

    resp = await client.patch(
        f"/api/v1/projects/{project.id}/tickets/{ticket.id}/fsm",
        json={"fsm_status": "specification"},
        headers=_auth(admin),
    )
    assert resp.status_code == 200
    assert resp.json()["fsm_status"] == "specification"


@pytest.mark.asyncio
async def test_fsm_patch_non_service_account_returns_403(
    client: AsyncClient, db_session: AsyncSession
):
    svc_email = f"svc-check-{uuid4()}@test.com"
    original_svc = settings.ticket_manager_service_email
    settings.ticket_manager_service_email = svc_email

    regular_user = await _user(db_session)  # email != svc_email, not admin
    owner = await _user(db_session, email=svc_email)
    project = await _project(db_session, owner)
    ticket = await _ticket(db_session, project, owner)
    await db_session.commit()

    try:
        resp = await client.patch(
            f"/api/v1/projects/{project.id}/tickets/{ticket.id}/fsm",
            json={"fsm_status": "triage"},
            headers=_auth(regular_user),
        )
        assert resp.status_code == 403
    finally:
        settings.ticket_manager_service_email = original_svc


@pytest.mark.asyncio
async def test_fsm_patch_unknown_ticket_returns_404(client: AsyncClient, db_session: AsyncSession):
    admin = await _user(db_session, role=UserRole.administrator)
    project = await _project(db_session, admin)
    await db_session.commit()

    resp = await client.patch(
        f"/api/v1/projects/{project.id}/tickets/{uuid4()}/fsm",
        json={"fsm_status": "triage"},
        headers=_auth(admin),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_fsm_patch_partial_update_only_changes_provided_field(
    client: AsyncClient, db_session: AsyncSession
):
    admin = await _user(db_session, role=UserRole.administrator)
    project = await _project(db_session, admin)
    ticket = await _ticket(db_session, project, admin, fsm_status="triage")
    await db_session.commit()

    resp = await client.patch(
        f"/api/v1/projects/{project.id}/tickets/{ticket.id}/fsm",
        json={"brainstorm_round": 3},
        headers=_auth(admin),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["brainstorm_round"] == 3
    assert data["fsm_status"] == "triage"  # unchanged


@pytest.mark.asyncio
async def test_fsm_patch_response_includes_all_fsm_fields(
    client: AsyncClient, db_session: AsyncSession
):
    admin = await _user(db_session, role=UserRole.administrator)
    project = await _project(db_session, admin)
    ticket = await _ticket(db_session, project, admin)
    await db_session.commit()

    resp = await client.patch(
        f"/api/v1/projects/{project.id}/tickets/{ticket.id}/fsm",
        json={"fsm_status": "backlog"},
        headers=_auth(admin),
    )
    assert resp.status_code == 200
    data = resp.json()
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
        assert field in data, f"Missing FSM field in response: {field}"


# ---------------------------------------------------------------------------
# T017 — POST /api/v1/tickets/{ticket_id}/audit  &  GET …/audit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_post_audit_event_returns_201_with_entry_id(
    client: AsyncClient, db_session: AsyncSession
):
    svc_email = f"svc-audit-{uuid4()}@test.com"
    original_svc = settings.ticket_manager_service_email
    settings.ticket_manager_service_email = svc_email

    svc_user = await _user(db_session, email=svc_email)
    project = await _project(db_session, svc_user)
    ticket = await _ticket(db_session, project, svc_user)
    await db_session.commit()

    try:
        resp = await client.post(
            f"/api/v1/tickets/{ticket.id}/audit",
            json={
                "event": "ADVANCE",
                "actor": "orchestrator",
                "from_state": "triage",
                "to_state": "specification",
                "details": "Auto-advance",
            },
            headers=_auth(svc_user),
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "id" in data
        assert data["event"] == "ADVANCE"
    finally:
        settings.ticket_manager_service_email = original_svc


@pytest.mark.asyncio
async def test_get_audit_log_returns_entries_in_chronological_order(
    client: AsyncClient, db_session: AsyncSession
):
    admin = await _user(db_session, role=UserRole.administrator)
    project = await _project(db_session, admin)
    ticket = await _ticket(db_session, project, admin)
    await db_session.commit()

    events = [
        {
            "event": "ADVANCE",
            "actor": "orchestrator",
            "from_state": "backlog",
            "to_state": "triage",
        },
        {"event": "BLOCK", "actor": "orchestrator", "from_state": "triage", "to_state": "BLOCKED"},
        {
            "event": "ADVANCE",
            "actor": "orchestrator",
            "from_state": "BLOCKED",
            "to_state": "triage",
        },
    ]
    for body in events:
        r = await client.post(
            f"/api/v1/tickets/{ticket.id}/audit",
            json=body,
            headers=_auth(admin),
        )
        assert r.status_code == 201

    resp = await client.get(f"/api/v1/tickets/{ticket.id}/audit", headers=_auth(admin))
    assert resp.status_code == 200
    entries = resp.json()["entries"]
    assert len(entries) == 3
    timestamps = [e["timestamp"] for e in entries]
    assert timestamps == sorted(timestamps)
    assert entries[0]["event"] == "ADVANCE"
    assert entries[1]["event"] == "BLOCK"
    assert entries[2]["event"] == "ADVANCE"


@pytest.mark.asyncio
async def test_get_audit_log_empty_when_no_events(client: AsyncClient, db_session: AsyncSession):
    user = await _user(db_session)
    project = await _project(db_session, user)
    ticket = await _ticket(db_session, project, user)
    await db_session.commit()

    resp = await client.get(f"/api/v1/tickets/{ticket.id}/audit", headers=_auth(user))
    assert resp.status_code == 200
    assert resp.json()["entries"] == []


@pytest.mark.asyncio
async def test_get_audit_log_unknown_ticket_returns_404(
    client: AsyncClient, db_session: AsyncSession
):
    user = await _user(db_session)
    await db_session.commit()

    resp = await client.get(f"/api/v1/tickets/{uuid4()}/audit", headers=_auth(user))
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_post_audit_non_service_account_returns_403(
    client: AsyncClient, db_session: AsyncSession
):
    """Security finding: POST /audit must be restricted to service-account-or-admin."""
    svc_email = f"svc-audit-sec-{uuid4()}@test.com"
    original_svc = settings.ticket_manager_service_email
    settings.ticket_manager_service_email = svc_email

    regular_user = await _user(db_session)  # not svc, not admin
    owner = await _user(db_session, email=svc_email)
    project = await _project(db_session, owner)
    ticket = await _ticket(db_session, project, owner)
    await db_session.commit()

    try:
        resp = await client.post(
            f"/api/v1/tickets/{ticket.id}/audit",
            json={"event": "ADVANCE", "actor": "rogue"},
            headers=_auth(regular_user),
        )
        assert resp.status_code == 403
    finally:
        settings.ticket_manager_service_email = original_svc


# ---------------------------------------------------------------------------
# T022 — POST /api/v1/projects/{project_id}/tickets/{ticket_id}/override
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_can_set_override(client: AsyncClient, db_session: AsyncSession):
    admin = await _user(db_session, role=UserRole.administrator)
    project = await _project(db_session, admin)
    ticket = await _ticket(db_session, project, admin)
    await db_session.commit()

    resp = await client.post(
        f"/api/v1/projects/{project.id}/tickets/{ticket.id}/override",
        json={"override": True, "override_reason": "Urgent hotfix approved by CTO"},
        headers=_auth(admin),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["override"] is True
    assert data["override_reason"] == "Urgent hotfix approved by CTO"


@pytest.mark.asyncio
async def test_non_admin_cannot_set_override(client: AsyncClient, db_session: AsyncSession):
    admin = await _user(db_session, role=UserRole.administrator)
    regular = await _user(db_session)
    project = await _project(db_session, admin)
    ticket = await _ticket(db_session, project, admin)
    await db_session.commit()

    resp = await client.post(
        f"/api/v1/projects/{project.id}/tickets/{ticket.id}/override",
        json={"override": True, "override_reason": "Bypass"},
        headers=_auth(regular),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_override_unknown_ticket_returns_404(client: AsyncClient, db_session: AsyncSession):
    admin = await _user(db_session, role=UserRole.administrator)
    project = await _project(db_session, admin)
    await db_session.commit()

    resp = await client.post(
        f"/api/v1/projects/{project.id}/tickets/{uuid4()}/override",
        json={"override": True, "override_reason": "Whatever"},
        headers=_auth(admin),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_override_reason_stored_correctly(client: AsyncClient, db_session: AsyncSession):
    admin = await _user(db_session, role=UserRole.administrator)
    project = await _project(db_session, admin)
    ticket = await _ticket(db_session, project, admin)
    await db_session.commit()

    reason = "Gate known-false-positive, approved in JIRA-123"
    resp = await client.post(
        f"/api/v1/projects/{project.id}/tickets/{ticket.id}/override",
        json={"override": True, "override_reason": reason},
        headers=_auth(admin),
    )
    assert resp.status_code == 200
    assert resp.json()["override_reason"] == reason


# ---------------------------------------------------------------------------
# T025 — POST /api/v1/tickets/batch-fsm-status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_batch_fsm_status_returns_correct_map(client: AsyncClient, db_session: AsyncSession):
    admin = await _user(db_session, role=UserRole.administrator)
    project = await _project(db_session, admin)
    t1 = await _ticket(db_session, project, admin, title="Alpha", fsm_status="triage")
    t2 = await _ticket(db_session, project, admin, title="Beta", fsm_status="implementation")
    t3 = await _ticket(db_session, project, admin, title="Gamma", fsm_status="done")
    await db_session.commit()

    resp = await client.post(
        "/api/v1/tickets/batch-fsm-status",
        json={"ticket_ids": [str(t1.id), str(t2.id), str(t3.id)]},
        headers=_auth(admin),
    )
    assert resp.status_code == 200
    statuses = resp.json()["statuses"]
    assert str(t1.id) in statuses
    assert statuses[str(t1.id)]["fsm_status"] == "triage"
    assert statuses[str(t1.id)]["title"] == "Alpha"
    assert str(t2.id) in statuses
    assert str(t3.id) in statuses


@pytest.mark.asyncio
async def test_batch_fsm_status_unknown_id_silently_omitted(
    client: AsyncClient, db_session: AsyncSession
):
    user = await _user(db_session)
    project = await _project(db_session, user)
    t1 = await _ticket(db_session, project, user, fsm_status="triage")
    unknown_id = str(uuid4())
    await db_session.commit()

    resp = await client.post(
        "/api/v1/tickets/batch-fsm-status",
        json={"ticket_ids": [str(t1.id), unknown_id]},
        headers=_auth(user),
    )
    assert resp.status_code == 200
    statuses = resp.json()["statuses"]
    assert str(t1.id) in statuses
    assert unknown_id not in statuses


@pytest.mark.asyncio
async def test_batch_fsm_status_empty_input_returns_empty_map(
    client: AsyncClient, db_session: AsyncSession
):
    user = await _user(db_session)
    await db_session.commit()

    resp = await client.post(
        "/api/v1/tickets/batch-fsm-status",
        json={"ticket_ids": []},
        headers=_auth(user),
    )
    assert resp.status_code == 200
    assert resp.json()["statuses"] == {}


@pytest.mark.asyncio
async def test_batch_fsm_status_blocked_ticket_includes_blocked_reason(
    client: AsyncClient, db_session: AsyncSession
):
    admin = await _user(db_session, role=UserRole.administrator)
    project = await _project(db_session, admin)
    ticket = await _ticket(db_session, project, admin, fsm_status="BLOCKED")
    await db_session.commit()

    # Set blocked_reason via FSM patch
    await client.patch(
        f"/api/v1/projects/{project.id}/tickets/{ticket.id}/fsm",
        json={"fsm_status": "BLOCKED", "blocked_reason": "Missing acceptance criteria"},
        headers=_auth(admin),
    )

    resp = await client.post(
        "/api/v1/tickets/batch-fsm-status",
        json={"ticket_ids": [str(ticket.id)]},
        headers=_auth(admin),
    )
    assert resp.status_code == 200
    entry = resp.json()["statuses"][str(ticket.id)]
    assert entry.get("blocked_reason") == "Missing acceptance criteria"


@pytest.mark.asyncio
async def test_batch_fsm_status_does_not_leak_cross_project_tickets(
    client: AsyncClient, db_session: AsyncSession
):
    """Security finding: batch endpoint must only return tickets in projects the caller can access."""
    user_a = await _user(db_session)
    user_b = await _user(db_session)
    project_a = await _project(db_session, user_a)
    project_b = await _project(db_session, user_b)
    ticket_a = await _ticket(db_session, project_a, user_a, fsm_status="triage")
    ticket_b = await _ticket(db_session, project_b, user_b, fsm_status="triage")
    await db_session.commit()

    # user_a requests both tickets — should NOT see ticket_b (different project, different owner)
    resp = await client.post(
        "/api/v1/tickets/batch-fsm-status",
        json={"ticket_ids": [str(ticket_a.id), str(ticket_b.id)]},
        headers=_auth(user_a),
    )
    assert resp.status_code == 200
    statuses = resp.json()["statuses"]
    # ticket_b belongs to a project user_a cannot access
    assert str(ticket_b.id) not in statuses


# ---------------------------------------------------------------------------
# T031 — GET /api/v1/projects/{project_id}/tickets/{ticket_id}/full
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_ticket_response_includes_all_fsm_fields(
    client: AsyncClient, db_session: AsyncSession
):
    admin = await _user(db_session, role=UserRole.administrator)
    project = await _project(db_session, admin)
    ticket = await _ticket(db_session, project, admin, fsm_status="specification")
    await db_session.commit()

    # Set all FSM fields via patch
    await client.patch(
        f"/api/v1/projects/{project.id}/tickets/{ticket.id}/fsm",
        json={
            "fsm_status": "specification",
            "blocked_reason": None,
            "brainstorm_round": 2,
            "assigned_agent": "agent-77",
        },
        headers=_auth(admin),
    )

    resp = await client.get(
        f"/api/v1/projects/{project.id}/tickets/{ticket.id}/full",
        headers=_auth(admin),
    )
    assert resp.status_code == 200
    data = resp.json()
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
        assert field in data, f"Missing FSM field: {field}"
    assert data["fsm_status"] == "specification"
    assert data["brainstorm_round"] == 2
    assert data["assigned_agent"] == "agent-77"


@pytest.mark.asyncio
async def test_full_ticket_fsm_defaults_when_unset(client: AsyncClient, db_session: AsyncSession):
    user = await _user(db_session)
    project = await _project(db_session, user)
    ticket = await _ticket(db_session, project, user)  # no FSM fields set
    await db_session.commit()

    resp = await client.get(
        f"/api/v1/projects/{project.id}/tickets/{ticket.id}/full",
        headers=_auth(user),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("brainstorm_round") == 0
    assert data.get("override") is False
    assert data.get("fsm_status") is None


@pytest.mark.asyncio
async def test_full_ticket_unknown_returns_404(client: AsyncClient, db_session: AsyncSession):
    user = await _user(db_session)
    project = await _project(db_session, user)
    await db_session.commit()

    resp = await client.get(
        f"/api/v1/projects/{project.id}/tickets/{uuid4()}/full",
        headers=_auth(user),
    )
    assert resp.status_code == 404
