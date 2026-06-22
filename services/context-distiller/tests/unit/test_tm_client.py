"""Unit tests for TMClient using respx."""

import httpx
import pytest
import respx
from src.core.exceptions import UpstreamError
from src.services.tm_client import TMClient


@pytest.fixture
def client():
    c = TMClient()
    return c


@respx.mock
async def test_get_ticket_success(client):
    respx.post("http://ticket-manager:8000/api/v1/auth/login").mock(
        return_value=httpx.Response(200, json={"access_token": "tok"})
    )
    respx.get("http://ticket-manager:8000/api/v1/tickets/T-001").mock(
        return_value=httpx.Response(200, json={"id": "T-001", "title": "Test"})
    )
    ticket = await client.get_ticket("T-001")
    assert ticket["id"] == "T-001"
    await client.aclose()


@respx.mock
async def test_get_ticket_not_found_raises_upstream(client):
    respx.post("http://ticket-manager:8000/api/v1/auth/login").mock(
        return_value=httpx.Response(200, json={"access_token": "tok"})
    )
    respx.get("http://ticket-manager:8000/api/v1/tickets/T-999").mock(
        return_value=httpx.Response(404, json={"detail": "not found"})
    )
    with pytest.raises(UpstreamError, match="not found"):
        await client.get_ticket("T-999")
    await client.aclose()


@respx.mock
async def test_get_ticket_server_error_raises_upstream(client):
    respx.post("http://ticket-manager:8000/api/v1/auth/login").mock(
        return_value=httpx.Response(200, json={"access_token": "tok"})
    )
    respx.get("http://ticket-manager:8000/api/v1/tickets/T-001").mock(
        return_value=httpx.Response(500, text="internal error")
    )
    with pytest.raises(UpstreamError):
        await client.get_ticket("T-001")
    await client.aclose()


@respx.mock
async def test_login_failure_raises_upstream(client):
    respx.post("http://ticket-manager:8000/api/v1/auth/login").mock(
        return_value=httpx.Response(401, json={"detail": "bad creds"})
    )
    with pytest.raises(UpstreamError, match="TM login failed"):
        await client.get_ticket("T-001")
    await client.aclose()


@respx.mock
async def test_get_ticket_events_success(client):
    respx.post("http://ticket-manager:8000/api/v1/auth/login").mock(
        return_value=httpx.Response(200, json={"access_token": "tok"})
    )
    respx.get("http://ticket-manager:8000/api/v1/tickets/T-001/events").mock(
        return_value=httpx.Response(200, json={"items": [{"event_type": "STATUS_CHANGE"}]})
    )
    events = await client.get_ticket_events("T-001")
    assert len(events) == 1
    assert events[0]["event_type"] == "STATUS_CHANGE"
    await client.aclose()


@respx.mock
async def test_get_ticket_events_failure_raises_upstream(client):
    respx.post("http://ticket-manager:8000/api/v1/auth/login").mock(
        return_value=httpx.Response(200, json={"access_token": "tok"})
    )
    respx.get("http://ticket-manager:8000/api/v1/tickets/T-001/events").mock(
        return_value=httpx.Response(503, text="unavailable")
    )
    with pytest.raises(UpstreamError):
        await client.get_ticket_events("T-001")
    await client.aclose()


@respx.mock
async def test_token_reused_on_second_call(client):
    login_route = respx.post("http://ticket-manager:8000/api/v1/auth/login").mock(
        return_value=httpx.Response(200, json={"access_token": "tok"})
    )
    respx.get("http://ticket-manager:8000/api/v1/tickets/T-001").mock(
        return_value=httpx.Response(200, json={"id": "T-001"})
    )
    await client.get_ticket("T-001")
    await client.get_ticket("T-001")
    # Login should only be called once
    assert login_route.call_count == 1
    await client.aclose()
