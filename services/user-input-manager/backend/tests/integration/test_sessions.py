"""Integration tests — /api/v1/sessions (prompt refinement loop)."""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from src.api.dependencies import get_session_service
from src.services.session_service import SessionService


def _make_svc(app, db, mock_tm_client, mock_llm_result):
    """Override session service to inject mock TM client and LLM."""

    async def _override_svc():
        return SessionService(db, mock_tm_client)

    app.dependency_overrides[get_session_service] = lambda: SessionService(db, mock_tm_client)
    return app


@pytest.mark.asyncio
async def test_create_session_new_project(
    client, app, db, auth_headers, mock_tm_client, mock_llm_result
):
    app.dependency_overrides[get_session_service] = lambda: SessionService(db, mock_tm_client)

    with patch(
        "src.services.session_service.refine_prompt", AsyncMock(return_value=mock_llm_result)
    ):
        resp = await client.post(
            "/api/v1/sessions",
            headers=auth_headers,
            json={
                "session_type": "new_project",
                "tm_project_name": "My New Project",
                "initial_prompt": "I want to build an auth system",
            },
        )

    assert resp.status_code == 201
    data = resp.json()
    assert "session" in data
    assert data["session"]["session_type"] == "new_project"
    assert "latest_iteration" in data
    assert data["latest_iteration"]["role"] == "assistant"
    assert data["latest_iteration"]["prompt_text"] == mock_llm_result.refined_prompt


@pytest.mark.asyncio
async def test_create_session_existing_project(
    client, app, db, auth_headers, mock_tm_client, mock_llm_result
):
    app.dependency_overrides[get_session_service] = lambda: SessionService(db, mock_tm_client)

    with patch(
        "src.services.session_service.refine_prompt", AsyncMock(return_value=mock_llm_result)
    ):
        resp = await client.post(
            "/api/v1/sessions",
            headers=auth_headers,
            json={
                "session_type": "existing_project",
                "tm_project_id": "proj-1",
                "initial_prompt": "Add OAuth login",
            },
        )

    assert resp.status_code == 201
    mock_tm_client.build_project_context.assert_awaited()


@pytest.mark.asyncio
async def test_get_iterations(client, app, db, auth_headers, mock_tm_client, mock_llm_result):
    app.dependency_overrides[get_session_service] = lambda: SessionService(db, mock_tm_client)

    with patch(
        "src.services.session_service.refine_prompt", AsyncMock(return_value=mock_llm_result)
    ):
        create_resp = await client.post(
            "/api/v1/sessions",
            headers=auth_headers,
            json={
                "session_type": "new_project",
                "tm_project_name": "Iter Test",
                "initial_prompt": "build something",
            },
        )
    session_id = create_resp.json()["session"]["id"]

    resp = await client.get(f"/api/v1/sessions/{session_id}/iterations", headers=auth_headers)
    assert resp.status_code == 200
    iterations = resp.json()
    assert len(iterations) == 2  # user + assistant
    assert iterations[0]["role"] == "user"
    assert iterations[1]["role"] == "assistant"


@pytest.mark.asyncio
async def test_submit_feedback_not_approved(
    client, app, db, auth_headers, mock_tm_client, mock_llm_result
):
    app.dependency_overrides[get_session_service] = lambda: SessionService(db, mock_tm_client)

    with patch(
        "src.services.session_service.refine_prompt", AsyncMock(return_value=mock_llm_result)
    ):
        create_resp = await client.post(
            "/api/v1/sessions",
            headers=auth_headers,
            json={
                "session_type": "new_project",
                "tm_project_name": "Feedback Test",
                "initial_prompt": "build something",
            },
        )
    session_id = create_resp.json()["session"]["id"]

    with patch(
        "src.services.session_service.refine_prompt", AsyncMock(return_value=mock_llm_result)
    ):
        resp = await client.post(
            f"/api/v1/sessions/{session_id}/feedback",
            headers=auth_headers,
            json={"is_approved": False, "comment": "Please add error handling"},
        )
    assert resp.status_code == 200
    assert resp.json()["awaiting_approval"] is False


@pytest.mark.asyncio
async def test_submit_feedback_approved(
    client, app, db, auth_headers, mock_tm_client, mock_llm_result
):
    app.dependency_overrides[get_session_service] = lambda: SessionService(db, mock_tm_client)

    with patch(
        "src.services.session_service.refine_prompt", AsyncMock(return_value=mock_llm_result)
    ):
        create_resp = await client.post(
            "/api/v1/sessions",
            headers=auth_headers,
            json={
                "session_type": "new_project",
                "tm_project_name": "Approve Test",
                "initial_prompt": "build something",
            },
        )
    session_id = create_resp.json()["session"]["id"]

    resp = await client.post(
        f"/api/v1/sessions/{session_id}/feedback",
        headers=auth_headers,
        json={"is_approved": True, "comment": "Looks great!"},
    )
    assert resp.status_code == 200
    assert resp.json()["awaiting_approval"] is True



@pytest.mark.asyncio
async def test_revert(client, app, db, auth_headers, mock_tm_client, mock_llm_result):
    app.dependency_overrides[get_session_service] = lambda: SessionService(db, mock_tm_client)

    with patch(
        "src.services.session_service.refine_prompt", AsyncMock(return_value=mock_llm_result)
    ):
        create_resp = await client.post(
            "/api/v1/sessions",
            headers=auth_headers,
            json={
                "session_type": "new_project",
                "tm_project_name": "Revert Test",
                "initial_prompt": "initial",
            },
        )
    session_id = create_resp.json()["session"]["id"]

    # Add another iteration
    with patch(
        "src.services.session_service.refine_prompt", AsyncMock(return_value=mock_llm_result)
    ):
        await client.post(
            f"/api/v1/sessions/{session_id}/feedback",
            headers=auth_headers,
            json={"is_approved": False, "comment": "more detail"},
        )

    # Revert to iteration 2 (first assistant)
    resp = await client.post(
        f"/api/v1/sessions/{session_id}/revert",
        headers=auth_headers,
        json={"target_iteration_number": 2},
    )
    assert resp.status_code == 200
    assert resp.json()["latest_iteration"]["iteration_number"] == 2
