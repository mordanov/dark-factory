"""Integration tests — /api/v1/orchestrator proxy endpoints."""
from unittest.mock import AsyncMock, patch

import pytest
from httpx import Response


def make_mock_response(status: int, data: dict):
    """Create a mock httpx.Response."""
    import httpx, json
    return httpx.Response(status_code=status, content=json.dumps(data).encode())


@pytest.mark.asyncio
async def test_pending_tickets_proxied(client, auth_headers):
    fake_data = {"tickets": [{"id": "t-1", "project_id": "p-1", "title": "T",
                               "description": "", "ticket_type": "feature",
                               "tags": [], "fsm_status": "triage",
                               "blocked_reason": None, "assigned_agent": None,
                               "brainstorm_round": 0, "dependencies": [],
                               "updated_at": None}], "total": 1}

    with patch("httpx.AsyncClient.request",
               new_callable=AsyncMock,
               return_value=make_mock_response(200, fake_data)):
        resp = await client.get("/api/v1/orchestrator/pending-tickets", headers=auth_headers)

    assert resp.status_code == 200
    assert resp.json()["total"] == 1


@pytest.mark.asyncio
async def test_trigger_job_proxied(client, auth_headers):
    fake_job = {"id": "job-1", "job_type": "orchestrate", "ticket_id": "t-1",
                "project_id": "p-1", "status": "pending", "priority": 0,
                "triggered_by": "uid-test", "error_message": None, "attempts": 0,
                "created_at": "2024-01-01T00:00:00Z", "started_at": None, "finished_at": None}

    with patch("httpx.AsyncClient.request",
               new_callable=AsyncMock,
               return_value=make_mock_response(201, fake_job)):
        resp = await client.post("/api/v1/orchestrator/jobs/trigger",
                                 headers=auth_headers,
                                 json={"ticket_id": "t-1", "project_id": "p-1"})

    assert resp.status_code == 201
    assert resp.json()["ticket_id"] == "t-1"


@pytest.mark.asyncio
async def test_orchestrator_requires_auth(client):
    resp = await client.get("/api/v1/orchestrator/pending-tickets")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_orchestrator_unavailable_returns_503(client, auth_headers):
    import httpx
    with patch("httpx.AsyncClient.request",
               new_callable=AsyncMock,
               side_effect=httpx.ConnectError("refused")):
        resp = await client.get("/api/v1/orchestrator/pending-tickets", headers=auth_headers)

    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_list_jobs_proxied(client, auth_headers):
    fake_jobs = {"items": [], "total": 0}
    with patch("httpx.AsyncClient.request",
               new_callable=AsyncMock,
               return_value=make_mock_response(200, fake_jobs)):
        resp = await client.get("/api/v1/orchestrator/jobs", headers=auth_headers)

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_audit_trail_proxied(client, auth_headers):
    fake_audit = {"items": [], "total": 0}
    with patch("httpx.AsyncClient.request",
               new_callable=AsyncMock,
               return_value=make_mock_response(200, fake_audit)):
        resp = await client.get("/api/v1/orchestrator/audit/t-1", headers=auth_headers)

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_project_memory_proxied(client, auth_headers):
    fake_mem = {"project_id": "p-1", "content": "yaml: ok", "version": 1,
                "last_ticket_id": None, "updated_at": None}
    with patch("httpx.AsyncClient.request",
               new_callable=AsyncMock,
               return_value=make_mock_response(200, fake_mem)):
        resp = await client.get("/api/v1/orchestrator/memory/p-1", headers=auth_headers)

    assert resp.status_code == 200
    assert resp.json()["content"] == "yaml: ok"
