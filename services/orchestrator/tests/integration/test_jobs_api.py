"""Integration tests — /api/v1/jobs endpoints."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from src.api.dependencies import get_current_user, get_tm
from src.services.tm_client.client import TicketManagerClient


def override_auth(app):
    app.dependency_overrides[get_current_user] = lambda: {"sub": "uid-test", "is_admin": False}


def override_tm(app, mock_tm):
    app.dependency_overrides[get_tm] = lambda: mock_tm


@pytest.mark.asyncio
async def test_list_pending_tickets(client, app, mock_tm):
    override_auth(app)
    override_tm(app, mock_tm)

    resp = await client.get("/api/v1/jobs/pending-tickets")
    assert resp.status_code == 200
    data = resp.json()
    assert "tickets" in data
    assert data["total"] == 1
    assert data["tickets"][0]["id"] == "t-1"


@pytest.mark.asyncio
async def test_list_pending_tickets_unauthenticated(client, app):
    app.dependency_overrides.pop(get_current_user, None)
    resp = await client.get("/api/v1/jobs/pending-tickets")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_trigger_job(client, app, mock_tm):
    override_auth(app)
    override_tm(app, mock_tm)

    with patch("src.api.v1.jobs.notify_new_job", new_callable=AsyncMock):
        resp = await client.post(
            "/api/v1/jobs/trigger",
            json={
                "ticket_id": "t-new",
                "project_id": "p-1",
                "priority": 3,
            },
        )

    assert resp.status_code == 201
    data = resp.json()
    assert data["ticket_id"] == "t-new"
    assert data["status"] == "pending"
    assert data["priority"] == 3


@pytest.mark.asyncio
async def test_trigger_job_conflict_when_running(client, app, db, mock_tm):
    override_auth(app)
    override_tm(app, mock_tm)

    from src.repositories.job_repo import JobRepository

    repo = JobRepository(db)
    job = await repo.create(
        job_type="orchestrate",
        ticket_id="t-running",
        project_id="p-1",
        triggered_by="u",
        payload={},
    )
    await repo.mark_running(job.id)

    with patch("src.api.v1.jobs.notify_new_job", new_callable=AsyncMock):
        resp = await client.post(
            "/api/v1/jobs/trigger",
            json={
                "ticket_id": "t-running",
                "project_id": "p-1",
            },
        )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_list_jobs(client, app, mock_tm):
    override_auth(app)

    with patch("src.api.v1.jobs.notify_new_job", new_callable=AsyncMock):
        await client.post("/api/v1/jobs/trigger", json={"ticket_id": "t-list", "project_id": "p-1"})

    resp = await client.get("/api/v1/jobs")
    assert resp.status_code == 200
    assert "items" in resp.json()


@pytest.mark.asyncio
async def test_get_job_not_found(client, app):
    override_auth(app)
    import uuid

    resp = await client.get(f"/api/v1/jobs/{uuid.uuid4()}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_health_endpoint(client):
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
