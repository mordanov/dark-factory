"""Scenario C — Orchestrator → ContextDistiller → project memory readable.

End-to-end flow: a user creates a ticket in TM, marks it done, triggers an
orchestrator job via the UIM proxy, polls until the job is "done", then
reads project memory and asserts it is non-null valid YAML with required keys.

Steps match data-model.md Scenario C:
  1. POST /api/v1/auth/login (TM) → already done via tm_auth_headers fixture
  2. Create a project and ticket in TM; PATCH ticket FSM to "done"
  3. POST /api/v1/orchestrator/jobs/trigger (UIM proxy) → job_id
  4. POLL GET /api/v1/orchestrator/jobs/{id} until status="done" (timeout: 30s)
  5. GET  /api/v1/orchestrator/memory/{project_id} (UIM proxy)
  Assert: memory_content is non-null
  Assert: parsed YAML has required top-level keys
"""
from __future__ import annotations

import asyncio

import httpx
import pytest
import yaml


# Keys mandated by the distiller YAML schema (orchestrator_service.py prompt)
REQUIRED_MEMORY_KEYS = {"project_id", "summary", "architecture", "tech_stack"}
JOB_POLL_TIMEOUT = 30  # seconds
JOB_POLL_INTERVAL = 1  # second


@pytest.mark.asyncio
async def test_scenario_c_orchestrator_memory(
    uim_client: httpx.AsyncClient,
    tm_client: httpx.AsyncClient,
    uim_auth_headers: dict[str, str],
    tm_auth_headers: dict[str, str],
):
    # Step 1: TM login already done via fixture.

    # Step 2a: Create a project in TM.
    import time
    project_name = f"Scenario C Project {int(time.time())}"
    resp = await tm_client.post(
        "/api/v1/projects",
        headers=tm_auth_headers,
        json={"name": project_name, "code": f"SC-C-{int(time.time()) % 100000}"},
    )
    assert resp.status_code == 201, f"TM project creation failed: {resp.status_code} {resp.text}"
    project = resp.json()
    tm_project_id = str(project["id"])

    # Step 2b: Create a ticket in TM.
    resp = await tm_client.post(
        f"/api/v1/projects/{tm_project_id}/tickets",
        headers=tm_auth_headers,
        json={
            "title": "Integration Test Ticket for Orchestration",
            "description": "Ticket created by Scenario C integration test.",
            "ticket_type": "feature",
        },
    )
    assert resp.status_code == 201, f"TM ticket creation failed: {resp.status_code} {resp.text}"
    ticket = resp.json()
    tm_ticket_id = str(ticket["id"])

    # Step 2c: Transition ticket FSM to "done".
    resp = await tm_client.post(
        f"/api/v1/tickets/{tm_ticket_id}/transitions",
        headers=tm_auth_headers,
        json={"to_status": "DONE"},
    )
    assert resp.status_code == 200, (
        f"TM ticket transition to DONE failed: {resp.status_code} {resp.text}"
    )

    # Step 3: Trigger orchestrator job via UIM proxy.
    resp = await uim_client.post(
        "/api/v1/orchestrator/jobs/trigger",
        headers=uim_auth_headers,
        json={"ticket_id": tm_ticket_id, "project_id": tm_project_id, "priority": 0},
    )
    assert resp.status_code == 201, (
        f"Orchestrator job trigger failed: {resp.status_code} {resp.text}"
    )
    job = resp.json()
    job_id = str(job["id"])

    # Step 4: Poll job status until done or timeout.
    deadline = asyncio.get_running_loop().time() + JOB_POLL_TIMEOUT
    final_status = None
    while asyncio.get_running_loop().time() < deadline:
        resp = await uim_client.get(
            f"/api/v1/orchestrator/jobs/{job_id}",
            headers=uim_auth_headers,
        )
        assert resp.status_code == 200, (
            f"Job poll failed: {resp.status_code} {resp.text}"
        )
        final_status = resp.json().get("status")
        if final_status in ("done", "failed", "error"):
            break
        await asyncio.sleep(JOB_POLL_INTERVAL)

    assert final_status == "done", (
        f"Job did not reach 'done' within {JOB_POLL_TIMEOUT}s — final status: {final_status!r}"
    )

    # Step 5: Read project memory via UIM proxy.
    resp = await uim_client.get(
        f"/api/v1/orchestrator/memory/{tm_project_id}",
        headers=uim_auth_headers,
    )
    assert resp.status_code == 200, (
        f"Project memory fetch failed: {resp.status_code} {resp.text}"
    )
    memory_response = resp.json()

    # Assert: memory content is non-null
    content = memory_response.get("content")
    assert content, "Project memory content is null or empty"

    # Assert: parsed YAML has required top-level keys
    try:
        parsed = yaml.safe_load(content)
    except yaml.YAMLError as exc:
        pytest.fail(f"Project memory is not valid YAML: {exc}\ncontent: {content[:200]!r}")

    assert isinstance(parsed, dict), (
        f"Expected YAML to parse to a dict, got {type(parsed).__name__}"
    )
    missing_keys = REQUIRED_MEMORY_KEYS - set(parsed.keys())
    assert not missing_keys, (
        f"Project memory YAML is missing required keys: {missing_keys}. "
        f"Keys present: {set(parsed.keys())}"
    )
