"""Unit tests for Reporter."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from src.schemas.schemas import AgentResult


def _kc_mock():
    mock_kc = MagicMock()
    mock_kc.async_auth_headers = AsyncMock(return_value={"Authorization": "Bearer svc-token"})
    return patch("src.services.reporter.get_kc_client", return_value=mock_kc)


async def test_report_result_posts_comment_and_triggers_orchestrator():
    with (
        patch("src.services.reporter.get_settings") as mock_settings,
        _kc_mock(),
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
        _kc_mock(),
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
        _kc_mock(),
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
        _kc_mock(),
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


async def test_report_result_includes_registry_yaml_in_trigger():
    """When a registry is passed, registry_yaml appears in the orchestrator trigger payload."""
    with (
        patch("src.services.reporter.get_settings") as mock_settings,
        _kc_mock(),
        patch("src.services.reporter.httpx.AsyncClient") as mock_client_cls,
    ):
        settings = MagicMock()
        settings.ticket_manager_base_url = "http://tm"
        settings.orchestrator_base_url = "http://orch"
        mock_settings.return_value = settings

        trigger_payloads: list = []

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()

        async def post_side_effect(url, **kwargs):
            if "trigger" in url:
                trigger_payloads.append(kwargs.get("json", {}))
            return mock_resp

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post.side_effect = post_side_effect
        mock_client_cls.return_value = mock_client

        mock_registry = MagicMock()
        mock_registry.to_yaml_string.return_value = "version: '1.0'\nagents: []"

        from src.services.reporter import Reporter

        reporter = Reporter()
        result = AgentResult(status="completed", summary="done", tm_comment="ok")
        await reporter.report_result("TKT-5", "proj-1", result, registry=mock_registry)

    assert len(trigger_payloads) == 1
    assert "registry_yaml" in trigger_payloads[0]
    assert "version" in trigger_payloads[0]["registry_yaml"]


async def test_report_result_no_registry_yaml_when_registry_none():
    """When registry is None, registry_yaml should not appear in the trigger payload."""
    with (
        patch("src.services.reporter.get_settings") as mock_settings,
        _kc_mock(),
        patch("src.services.reporter.httpx.AsyncClient") as mock_client_cls,
    ):
        settings = MagicMock()
        settings.ticket_manager_base_url = "http://tm"
        settings.orchestrator_base_url = "http://orch"
        mock_settings.return_value = settings

        trigger_payloads: list = []

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()

        async def post_side_effect(url, **kwargs):
            if "trigger" in url:
                trigger_payloads.append(kwargs.get("json", {}))
            return mock_resp

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post.side_effect = post_side_effect
        mock_client_cls.return_value = mock_client

        from src.services.reporter import Reporter

        reporter = Reporter()
        result = AgentResult(status="completed", summary="done", tm_comment="ok")
        await reporter.report_result("TKT-6", "proj-1", result, registry=None)

    assert len(trigger_payloads) == 1
    assert "registry_yaml" not in trigger_payloads[0]


# ---------------------------------------------------------------------------
# T012 / T015 / T017 — brainstorm_transcript tests
# ---------------------------------------------------------------------------


def _make_transcript(messages=None):
    from src.services.brainstorm.cli_reader import BrainstormMessage, BrainstormTranscript

    msgs = (
        messages
        if messages is not None
        else [
            BrainstormMessage(
                author="software-architect", content="Use CQRS.", timestamp="2026-01-01T00:00:00Z"
            ),
        ]
    )
    return BrainstormTranscript(
        project_name="df-TKT-1",
        round_number=1,
        max_rounds=3,
        messages=msgs,
        consensus="inconclusive",
    )


async def test_report_result_includes_transcript_in_payload():
    """brainstorm_result with transcript → payload["brainstorm_transcript"] present."""
    with (
        patch("src.services.reporter.get_settings") as mock_settings,
        _kc_mock(),
        patch("src.services.reporter.httpx.AsyncClient") as mock_client_cls,
    ):
        settings = MagicMock()
        settings.ticket_manager_base_url = "http://tm"
        settings.orchestrator_base_url = "http://orch"
        mock_settings.return_value = settings

        trigger_payloads: list = []
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()

        async def post_side_effect(url, **kwargs):
            if "trigger" in url:
                trigger_payloads.append(kwargs.get("json", {}))
            return mock_resp

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post.side_effect = post_side_effect
        mock_client_cls.return_value = mock_client

        from src.services.reporter import Reporter

        reporter = Reporter()
        result = AgentResult(status="completed", summary="done", tm_comment="ok")
        brainstorm_result = {"transcript": _make_transcript()}
        await reporter.report_result("TKT-1", "proj-1", result, brainstorm_result=brainstorm_result)

    assert len(trigger_payloads) == 1
    assert "brainstorm_transcript" in trigger_payloads[0]
    bt = trigger_payloads[0]["brainstorm_transcript"]
    assert bt["project_name"] == "df-TKT-1"
    assert bt["round_number"] == 1
    assert bt["max_rounds"] == 3
    assert bt["consensus"] == "inconclusive"
    assert len(bt["messages"]) == 1
    assert bt["messages"][0]["author"] == "software-architect"
    assert bt["messages"][0]["content"] == "Use CQRS."
    assert bt["messages"][0]["timestamp"] == "2026-01-01T00:00:00Z"


async def test_report_result_no_transcript_when_none():
    """brainstorm_result=None → no brainstorm_transcript key in trigger payload."""
    with (
        patch("src.services.reporter.get_settings") as mock_settings,
        _kc_mock(),
        patch("src.services.reporter.httpx.AsyncClient") as mock_client_cls,
    ):
        settings = MagicMock()
        settings.ticket_manager_base_url = "http://tm"
        settings.orchestrator_base_url = "http://orch"
        mock_settings.return_value = settings

        trigger_payloads: list = []
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()

        async def post_side_effect(url, **kwargs):
            if "trigger" in url:
                trigger_payloads.append(kwargs.get("json", {}))
            return mock_resp

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post.side_effect = post_side_effect
        mock_client_cls.return_value = mock_client

        from src.services.reporter import Reporter

        reporter = Reporter()
        result = AgentResult(status="completed", summary="done", tm_comment="ok")
        await reporter.report_result("TKT-2", "proj-1", result, brainstorm_result=None)

    assert "brainstorm_transcript" not in trigger_payloads[0]


async def test_report_result_empty_messages_list_included():
    """Transcript with messages=[] → payload still includes brainstorm_transcript with empty list."""
    with (
        patch("src.services.reporter.get_settings") as mock_settings,
        _kc_mock(),
        patch("src.services.reporter.httpx.AsyncClient") as mock_client_cls,
    ):
        settings = MagicMock()
        settings.ticket_manager_base_url = "http://tm"
        settings.orchestrator_base_url = "http://orch"
        mock_settings.return_value = settings

        trigger_payloads: list = []
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()

        async def post_side_effect(url, **kwargs):
            if "trigger" in url:
                trigger_payloads.append(kwargs.get("json", {}))
            return mock_resp

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post.side_effect = post_side_effect
        mock_client_cls.return_value = mock_client

        from src.services.reporter import Reporter

        reporter = Reporter()
        result = AgentResult(status="completed", summary="done", tm_comment="ok")
        brainstorm_result = {"transcript": _make_transcript(messages=[])}
        await reporter.report_result("TKT-3", "proj-1", result, brainstorm_result=brainstorm_result)

    bt = trigger_payloads[0]["brainstorm_transcript"]
    assert bt["messages"] == []


async def test_no_brainstorm_transcript_for_non_architecture_review():
    """Regular (non-brainstorm) report_result call omits brainstorm_transcript from payload."""
    with (
        patch("src.services.reporter.get_settings") as mock_settings,
        _kc_mock(),
        patch("src.services.reporter.httpx.AsyncClient") as mock_client_cls,
    ):
        settings = MagicMock()
        settings.ticket_manager_base_url = "http://tm"
        settings.orchestrator_base_url = "http://orch"
        mock_settings.return_value = settings

        trigger_payloads: list = []
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()

        async def post_side_effect(url, **kwargs):
            if "trigger" in url:
                trigger_payloads.append(kwargs.get("json", {}))
            return mock_resp

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post.side_effect = post_side_effect
        mock_client_cls.return_value = mock_client

        from src.services.reporter import Reporter

        reporter = Reporter()
        result = AgentResult(status="completed", summary="done", tm_comment="ok")
        # Simulating a non-brainstorm call site — no brainstorm_result passed
        await reporter.report_result("TKT-4", "proj-1", result)

    assert "brainstorm_transcript" not in trigger_payloads[0]
