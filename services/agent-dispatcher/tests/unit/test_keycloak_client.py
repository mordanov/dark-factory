"""Unit tests for KeycloakServiceClient (src.core.keycloak_client) — agent-dispatcher.

Tests: token caching, 30s-before-expiry refresh, asyncio.Lock concurrency, error handling.
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_token_response(expires_in: int = 300) -> dict:
    return {
        "access_token": "eyJhbGciOiJSUzI1NiJ9.test.token",
        "token_type": "Bearer",
        "expires_in": expires_in,
    }


def _make_client(
    base_url: str = "http://keycloak:8080",
    realm: str = "dark-factory",
    client_id: str = "agent-dispatcher",
    client_secret: str = "test-secret",
):
    from src.core.keycloak_client import KeycloakServiceClient

    return KeycloakServiceClient(
        keycloak_base_url=base_url,
        realm=realm,
        client_id=client_id,
        client_secret=client_secret,
    )


@pytest.mark.asyncio
async def test_get_token_calls_keycloak_token_endpoint():
    """Cold cache: get_token() calls the KC token endpoint and returns the token string."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = _make_token_response()

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_http = AsyncMock()
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_http.post = AsyncMock(return_value=mock_response)

        client = _make_client()
        token = await client.get_token()

    assert token == "eyJhbGciOiJSUzI1NiJ9.test.token"
    mock_http.post.assert_called_once()
    call_url = mock_http.post.call_args[0][0]
    assert "openid-connect/token" in call_url


@pytest.mark.asyncio
async def test_token_cached_until_expiry():
    """Two sequential get_token() calls within cache window hit KC only once."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = _make_token_response(expires_in=300)

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_http = AsyncMock()
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_http.post = AsyncMock(return_value=mock_response)

        client = _make_client()
        token1 = await client.get_token()
        token2 = await client.get_token()

    assert token1 == token2
    assert mock_http.post.call_count == 1


@pytest.mark.asyncio
async def test_token_refreshed_30s_before_expiry():
    """Second call when token is within 30s of expiry triggers a new fetch."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = _make_token_response(expires_in=300)

    with patch("httpx.AsyncClient") as mock_client_cls, patch("time.monotonic") as mock_time:
        mock_http = AsyncMock()
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_http.post = AsyncMock(return_value=mock_response)

        mock_time.side_effect = [0.0, 280.0, 280.0]

        client = _make_client()
        await client.get_token()
        await client.get_token()

    assert mock_http.post.call_count == 2


@pytest.mark.asyncio
async def test_concurrent_calls_use_single_request():
    """Two concurrent get_token() calls on a cold cache result in exactly one KC request."""
    call_count = 0
    original_token = "concurrent-token-value"

    async def fake_post(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        await asyncio.sleep(0.01)
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"access_token": original_token, "expires_in": 300}
        return resp

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_http = AsyncMock()
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_http.post = fake_post

        client = _make_client()
        results = await asyncio.gather(client.get_token(), client.get_token())

    assert call_count == 1
    assert results[0] == original_token
    assert results[1] == original_token


@pytest.mark.asyncio
async def test_keycloak_error_raises_upstream_error():
    """Non-200 response from KC token endpoint raises UpstreamError."""
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.text = "Internal Server Error"

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_http = AsyncMock()
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_http.post = AsyncMock(return_value=mock_response)

        from src.core.keycloak_client import KeycloakServiceClient, UpstreamError

        client = KeycloakServiceClient(
            keycloak_base_url="http://keycloak:8080",
            realm="dark-factory",
            client_id="agent-dispatcher",
            client_secret="test-secret",
        )

        with pytest.raises(UpstreamError):
            await client.get_token()


@pytest.mark.asyncio
async def test_client_secret_not_in_upstream_error():
    """UpstreamError message must not contain the client secret (FIND-01)."""
    secret = "super-sensitive-client-secret"
    mock_response = MagicMock()
    mock_response.status_code = 401
    mock_response.text = "Unauthorized"

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_http = AsyncMock()
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_http.post = AsyncMock(return_value=mock_response)

        from src.core.keycloak_client import KeycloakServiceClient, UpstreamError

        client = KeycloakServiceClient(
            keycloak_base_url="http://keycloak:8080",
            realm="dark-factory",
            client_id="agent-dispatcher",
            client_secret=secret,
        )

        with pytest.raises(UpstreamError) as exc_info:
            await client.get_token()

        assert secret not in str(exc_info.value)
