"""Integration tests for poller (mocked Orchestrator httpx client)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest


async def test_returns_only_assigned_tickets(db_session):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "tickets": [
            {
                "id": "TKT-1",
                "project_id": "proj-1",
                "assigned_agent": "backend",
                "fsm_status": "implementation",
                "ticket_type": "feature",
                "title": "Test",
                "description": "Desc",
            },
            {
                "id": "TKT-2",
                "project_id": "proj-1",
                "assigned_agent": None,
                "fsm_status": "pending",
                "ticket_type": "feature",
                "title": "Test2",
                "description": "Desc2",
            },
        ]
    }
    mock_response.raise_for_status = MagicMock()

    with patch("src.services.poller.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_cls.return_value = mock_client

        with patch("src.services.poller.get_settings") as mock_settings:
            settings = MagicMock()
            settings.orchestrator_base_url = "http://mock-orchestrator"
            mock_settings.return_value = settings

            with patch("src.services.poller.create_service_token", return_value="jwt"):
                from src.services.poller import poll_once

                tickets = await poll_once(db_session)

    assert len(tickets) == 1
    assert tickets[0].id == "TKT-1"


async def test_filters_out_tickets_with_running_run(db_session):
    from src.repositories.run_repo import AgentRunRepository

    repo = AgentRunRepository(db_session)
    run = await repo.create(
        ticket_id="TKT-RUNNING",
        project_id="proj-1",
        agent_id="backend",
        runner_mode="claude_code",
        context_snapshot={},
    )
    await repo.mark_running(run.id)
    await db_session.commit()

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "tickets": [
            {
                "id": "TKT-RUNNING",
                "project_id": "proj-1",
                "assigned_agent": "backend",
                "fsm_status": "implementation",
                "ticket_type": "feature",
                "title": "Running",
                "description": "desc",
            },
        ]
    }
    mock_response.raise_for_status = MagicMock()

    with patch("src.services.poller.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_cls.return_value = mock_client

        with patch("src.services.poller.get_settings") as mock_settings:
            settings = MagicMock()
            settings.orchestrator_base_url = "http://mock-orchestrator"
            mock_settings.return_value = settings

            with patch("src.services.poller.create_service_token", return_value="jwt"):
                from src.services.poller import poll_once

                tickets = await poll_once(db_session)

    assert len(tickets) == 0


async def test_handles_orchestrator_503_gracefully(db_session):
    with patch("src.services.poller.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                "503", request=MagicMock(), response=MagicMock(status_code=503)
            )
        )
        mock_cls.return_value = mock_client

        with patch("src.services.poller.get_settings") as mock_settings:
            settings = MagicMock()
            settings.orchestrator_base_url = "http://mock-orchestrator"
            mock_settings.return_value = settings

            with patch("src.services.poller.create_service_token", return_value="jwt"):
                from src.services.poller import poll_once

                tickets = await poll_once(db_session)

    assert tickets == []
