"""Unit tests for TMClient using respx."""

import httpx
import pytest
import respx
from unittest.mock import AsyncMock, patch
from src.core.exceptions import UpstreamError
from src.services.tm_client import TMClient


@pytest.fixture
def client():
    return TMClient()


def _kc_headers():
    """Patch get_kc_client to return a mock that yields a fixed auth header."""
    mock_kc = AsyncMock()
    mock_kc.async_auth_headers = AsyncMock(return_value={"Authorization": "Bearer tok"})
    return patch("src.services.tm_client.get_kc_client", return_value=mock_kc)


@respx.mock
async def test_get_ticket_success(client):
    with _kc_headers():
        respx.get("http://ticket-manager:8000/api/v1/tickets/T-001").mock(
            return_value=httpx.Response(200, json={"id": "T-001", "title": "Test"})
        )
        ticket = await client.get_ticket("T-001")
        assert ticket["id"] == "T-001"
    await client.aclose()


@respx.mock
async def test_get_ticket_not_found_raises_upstream(client):
    with _kc_headers():
        respx.get("http://ticket-manager:8000/api/v1/tickets/T-999").mock(
            return_value=httpx.Response(404, json={"detail": "not found"})
        )
        with pytest.raises(UpstreamError, match="not found"):
            await client.get_ticket("T-999")
    await client.aclose()


@respx.mock
async def test_get_ticket_server_error_raises_upstream(client):
    with _kc_headers():
        respx.get("http://ticket-manager:8000/api/v1/tickets/T-001").mock(
            return_value=httpx.Response(500, text="internal error")
        )
        with pytest.raises(UpstreamError):
            await client.get_ticket("T-001")
    await client.aclose()


@respx.mock
async def test_get_ticket_events_success(client):
    with _kc_headers():
        respx.get("http://ticket-manager:8000/api/v1/tickets/T-001/events").mock(
            return_value=httpx.Response(200, json={"items": [{"event_type": "STATUS_CHANGE"}]})
        )
        events = await client.get_ticket_events("T-001")
        assert len(events) == 1
        assert events[0]["event_type"] == "STATUS_CHANGE"
    await client.aclose()


@respx.mock
async def test_get_ticket_events_failure_raises_upstream(client):
    with _kc_headers():
        respx.get("http://ticket-manager:8000/api/v1/tickets/T-001/events").mock(
            return_value=httpx.Response(503, text="unavailable")
        )
        with pytest.raises(UpstreamError):
            await client.get_ticket_events("T-001")
    await client.aclose()


@respx.mock
async def test_auth_header_passed_on_each_call(client):
    call_count = 0
    mock_kc = AsyncMock()

    async def _headers():
        nonlocal call_count
        call_count += 1
        return {"Authorization": "Bearer tok"}

    mock_kc.async_auth_headers = _headers

    with patch("src.services.tm_client.get_kc_client", return_value=mock_kc):
        respx.get("http://ticket-manager:8000/api/v1/tickets/T-001").mock(
            return_value=httpx.Response(200, json={"id": "T-001"})
        )
        await client.get_ticket("T-001")
        await client.get_ticket("T-001")

    # auth headers fetched for each call (KC client handles caching internally)
    assert call_count == 2
    await client.aclose()
