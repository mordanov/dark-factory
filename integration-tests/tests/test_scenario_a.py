"""Scenario A — UIM → TM ticket creation.

End-to-end flow: a user logs into Prompt Studio (UIM), creates a session,
goes through a feedback loop, approves the prompt, and the resulting ticket
appears in Ticket Manager with the tag "needs-estimation" and a description
prefixed "[needs-estimation]".

Steps match data-model.md Scenario A:
  1. POST /api/v1/auth/login (UIM)
  2. POST /api/v1/sessions (UIM)
  3. POST /api/v1/sessions/{id}/feedback {is_approved: false}
  4. POST /api/v1/sessions/{id}/feedback {is_approved: true}
  5. POST /api/v1/sessions/{id}/approve {ticket_title, project_description}
  6. GET  /api/v1/projects/{project_id}/tickets (TM)
  Assert: ticket.tags contains "needs-estimation"
  Assert: ticket.description starts with "[needs-estimation]"
"""
from __future__ import annotations

import pytest
import httpx


@pytest.mark.asyncio
async def test_scenario_a_uim_to_tm_ticket_creation(
    uim_client: httpx.AsyncClient,
    tm_client: httpx.AsyncClient,
    uim_auth_headers: dict[str, str],
    tm_auth_headers: dict[str, str],
):
    # Step 1: Login already done — uim_auth_headers fixture handles it.
    # Step 2: Create a new session (new project, no existing TM project).
    resp = await uim_client.post(
        "/api/v1/sessions",
        headers=uim_auth_headers,
        json={
            "session_type": "new_project",
            "tm_project_name": "Integration Test Project A",
        },
    )
    assert resp.status_code == 201, f"Session creation failed: {resp.status_code} {resp.text}"
    session = resp.json()
    session_id = session["id"]

    # Step 3: Submit negative feedback (is_approved=false) — triggers LLM iteration.
    resp = await uim_client.post(
        f"/api/v1/sessions/{session_id}/feedback",
        headers=uim_auth_headers,
        json={"is_approved": False, "comment": "Please make the description more detailed."},
    )
    assert resp.status_code in (200, 201), (
        f"Negative feedback failed: {resp.status_code} {resp.text}"
    )

    # Step 4: Submit positive feedback (is_approved=true) — accept the latest iteration.
    resp = await uim_client.post(
        f"/api/v1/sessions/{session_id}/feedback",
        headers=uim_auth_headers,
        json={"is_approved": True, "comment": "Looks good."},
    )
    assert resp.status_code in (200, 201), (
        f"Positive feedback failed: {resp.status_code} {resp.text}"
    )

    # Step 5: Approve session — creates TM project + ticket.
    ticket_title = "Integration Test Ticket from Scenario A"
    resp = await uim_client.post(
        f"/api/v1/sessions/{session_id}/approve",
        headers=uim_auth_headers,
        json={
            "ticket_title": ticket_title,
            "project_description": "A project created by integration test Scenario A.",
        },
    )
    assert resp.status_code in (200, 201), (
        f"Approve failed: {resp.status_code} {resp.text}"
    )
    approve_result = resp.json()
    ticket_id = approve_result["ticket_id"]
    project_id = approve_result["project_id"]
    assert ticket_id, "approve_and_create_ticket returned no ticket_id"
    assert project_id, "approve_and_create_ticket returned no project_id"

    # Step 6: Fetch ticket from TM and verify assertions.
    resp = await tm_client.get(
        f"/api/v1/tickets/{ticket_id}",
        headers=tm_auth_headers,
    )
    assert resp.status_code == 200, (
        f"TM ticket fetch failed: {resp.status_code} {resp.text}"
    )
    ticket = resp.json()

    # Assert: tag "needs-estimation" is present
    tag_names = [t["name"] if isinstance(t, dict) else t for t in ticket.get("tags", [])]
    assert "needs-estimation" in tag_names, (
        f"Expected tag 'needs-estimation' in {tag_names}"
    )

    # Assert: description starts with "[needs-estimation]"
    description = ticket.get("description", "")
    assert description.startswith("[needs-estimation]"), (
        f"Expected description to start with '[needs-estimation]', got: {description[:80]!r}"
    )
