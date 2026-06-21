"""Integration tests for distill enqueue and job status endpoints."""
import uuid
import pytest


async def test_enqueue_distill_returns_202(test_client):
    resp = await test_client.post(
        "/distill",
        json={"ticket_id": "T-001", "project_id": "proj-1"},
    )
    assert resp.status_code == 202
    data = resp.json()
    assert "job_id" in data
    # Validate it's a valid UUID
    uuid.UUID(data["job_id"])


async def test_get_job_status_pending(test_client, db_session):
    # Enqueue a job
    enq_resp = await test_client.post(
        "/distill",
        json={"ticket_id": "T-001", "project_id": "proj-1"},
    )
    job_id = enq_resp.json()["job_id"]

    resp = await test_client.get(f"/status/{job_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["job_id"] == job_id
    assert data["status"] in ("pending", "running", "done", "failed")
    assert data["error"] is None


async def test_get_job_status_not_found(test_client):
    fake_id = str(uuid.uuid4())
    resp = await test_client.get(f"/status/{fake_id}")
    assert resp.status_code == 404


async def test_health_endpoint(test_client):
    resp = await test_client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
