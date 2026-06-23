"""Unit tests for Reporter."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from src.schemas.schemas import AgentResult


async def test_report_result_posts_comment_and_triggers_orchestrator():
    with (
        patch("src.services.reporter.get_settings") as mock_settings,
        patch("src.services.reporter.create_service_token", return_value="svc-token"),
        patch("src.services.reporter.httpx.AsyncClient") as mock_client_cls,
    ):
        settings = MagicMock()
        settings.ticket_manager_base_url = "http://tm"
        settings.orchestrator_base_url = "http://orch"
        mock_settings.return_value = settings

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value = mock_client

        from src.services.reporter import Reporter

        reporter = Reporter()
        result = AgentResult(status="completed", summary="done", tm_comment="Great work")
        await reporter.report_result("TKT-1", "proj-1", result)

    assert mock_client.post.call_count == 2


async def test_report_result_uses_summary_when_no_tm_comment():
    with (
        patch("src.services.reporter.get_settings") as mock_settings,
        patch("src.services.reporter.create_service_token", return_value="svc-token"),
        patch("src.services.reporter.httpx.AsyncClient") as mock_client_cls,
    ):
        settings = MagicMock()
        settings.ticket_manager_base_url = "http://tm"
        settings.orchestrator_base_url = "http://orch"
        mock_settings.return_value = settings

        posted_bodies = []

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()

        async def post_side_effect(url, **kwargs):
            posted_bodies.append(kwargs.get("json", {}))
            return mock_resp

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post.side_effect = post_side_effect
        mock_client_cls.return_value = mock_client

        from src.services.reporter import Reporter

        reporter = Reporter()
        result = AgentResult(status="completed", summary="summary text", tm_comment="")
        await reporter.report_result("TKT-2", "proj-1", result)

    assert posted_bodies[0]["content"] == "summary text"


async def test_tm_comment_failure_is_swallowed():
    with (
        patch("src.services.reporter.get_settings") as mock_settings,
        patch("src.services.reporter.create_service_token", return_value="svc-token"),
        patch("src.services.reporter.httpx.AsyncClient") as mock_client_cls,
    ):
        settings = MagicMock()
        settings.ticket_manager_base_url = "http://tm"
        settings.orchestrator_base_url = "http://orch"
        mock_settings.return_value = settings

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(
            side_effect=[Exception("TM down"), MagicMock(raise_for_status=MagicMock())]
        )
        mock_client_cls.return_value = mock_client

        from src.services.reporter import Reporter

        reporter = Reporter()
        result = AgentResult(status="completed", summary="s", tm_comment="c")
        # Should not raise even though TM is down
        await reporter.report_result("TKT-3", "proj-1", result)


async def test_orchestrator_trigger_retries_once():
    """First orch trigger fails, second succeeds → exactly 3 POST calls total."""
    with (
        patch("src.services.reporter.get_settings") as mock_settings,
        patch("src.services.reporter.create_service_token", return_value="svc-token"),
        patch("src.services.reporter.httpx.AsyncClient") as mock_client_cls,
    ):
        settings = MagicMock()
        settings.ticket_manager_base_url = "http://tm"
        settings.orchestrator_base_url = "http://orch"
        mock_settings.return_value = settings

        call_count = 0

        mock_resp_ok = MagicMock()
        mock_resp_ok.raise_for_status = MagicMock()

        async def post_side_effect(url, **kwargs):
            nonlocal call_count
            call_count += 1
            if "trigger" in url and call_count == 2:
                # First orchestrator attempt fails
                raise httpx.HTTPError("orch down")
            return mock_resp_ok

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post.side_effect = post_side_effect
        mock_client_cls.return_value = mock_client

        from src.services.reporter import Reporter

        reporter = Reporter()
        result = AgentResult(status="completed", summary="s", tm_comment="c")
        await reporter.report_result("TKT-4", "proj-1", result)

    # 1 TM comment + 2 orchestrator trigger attempts = 3 total
    assert call_count == 3
