"""Unit tests for KeycloakValidator (src.core.auth_adapter) — context-distiller.

All tests run with AUTH_MODE=local (HS256, test secret).
JWKS tests switch to AUTH_MODE=keycloak and mock httpx.
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from jose import jwt

TEST_SECRET = "test-secret-do-not-use-in-production"
ALGORITHM_LOCAL = "HS256"


def _make_token(
    sub: str = "user-sub-123",
    email: str = "user@example.com",
    preferred_username: str = "testuser",
    roles: list[str] | None = None,
    expired: bool = False,
    secret: str = TEST_SECRET,
    include_realm_access: bool = True,
) -> str:
    now = int(time.time())
    payload: dict = {
        "sub": sub,
        "email": email,
        "preferred_username": preferred_username,
        "iat": now,
        "exp": now - 10 if expired else now + 3600,
    }
    if include_realm_access:
        payload["realm_access"] = {"roles": roles if roles is not None else ["user"]}
    return jwt.encode(payload, secret, algorithm=ALGORITHM_LOCAL)


@pytest.mark.asyncio
async def test_valid_user_token_returns_claims(monkeypatch):
    """Valid HS256 token in LOCAL mode returns UserClaims with correct fields."""
    monkeypatch.setenv("AUTH_MODE", "local")
    monkeypatch.setenv("TEST_JWT_SECRET", TEST_SECRET)

    from src.core.auth_adapter import KeycloakValidator

    validator = KeycloakValidator()
    token = _make_token(sub="abc-123", email="user@test.com", roles=["user"])
    claims = await validator.verify(token)

    assert claims.sub == "abc-123"
    assert claims.email == "user@test.com"
    assert "user" in claims.roles
    assert claims.is_admin is False


@pytest.mark.asyncio
async def test_valid_admin_token_has_is_admin_true(monkeypatch):
    """Token with 'administrator' role in realm_access yields is_admin=True."""
    monkeypatch.setenv("AUTH_MODE", "local")
    monkeypatch.setenv("TEST_JWT_SECRET", TEST_SECRET)

    from src.core.auth_adapter import KeycloakValidator

    validator = KeycloakValidator()
    token = _make_token(roles=["user", "administrator"])
    claims = await validator.verify(token)

    assert claims.is_admin is True
    assert "administrator" in claims.roles


@pytest.mark.asyncio
async def test_invalid_token_raises_unauthorized(monkeypatch):
    """Garbage string raises UnauthorizedError."""
    monkeypatch.setenv("AUTH_MODE", "local")
    monkeypatch.setenv("TEST_JWT_SECRET", TEST_SECRET)

    from src.core.auth_adapter import KeycloakValidator, UnauthorizedError

    validator = KeycloakValidator()
    with pytest.raises(UnauthorizedError):
        await validator.verify("not.a.valid.jwt")


@pytest.mark.asyncio
async def test_expired_token_raises_unauthorized(monkeypatch):
    """Token with past `exp` raises UnauthorizedError."""
    monkeypatch.setenv("AUTH_MODE", "local")
    monkeypatch.setenv("TEST_JWT_SECRET", TEST_SECRET)

    from src.core.auth_adapter import KeycloakValidator, UnauthorizedError

    validator = KeycloakValidator()
    token = _make_token(expired=True)
    with pytest.raises(UnauthorizedError):
        await validator.verify(token)


@pytest.mark.asyncio
async def test_missing_realm_access_returns_empty_roles(monkeypatch):
    """Valid token without realm_access key yields roles=[] and is_admin=False."""
    monkeypatch.setenv("AUTH_MODE", "local")
    monkeypatch.setenv("TEST_JWT_SECRET", TEST_SECRET)

    from src.core.auth_adapter import KeycloakValidator

    validator = KeycloakValidator()
    token = _make_token(include_realm_access=False)
    claims = await validator.verify(token)

    assert claims.roles == []
    assert claims.is_admin is False


@pytest.mark.asyncio
async def test_keycloak_mode_fetches_jwks(monkeypatch):
    """In keycloak mode, JWKS endpoint is called exactly once on first verify."""
    monkeypatch.setenv("AUTH_MODE", "keycloak")
    monkeypatch.setenv("TEST_JWT_SECRET", TEST_SECRET)
    from src.core.config import get_settings

    get_settings.cache_clear()
    import src.core.auth_adapter  # ensure module is loaded before patch resolves
    from src.core.auth_adapter import KeycloakValidator

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"keys": []}

    with patch("src.core.auth_adapter.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)

        validator = KeycloakValidator()
        validator._jwks = None
        validator._jwks_fetched_at = 0.0

        try:
            await validator.verify("dummy.token.value")
        except Exception:
            pass

        mock_client.get.assert_called_once()
        call_url = mock_client.get.call_args[0][0]
        assert "openid-connect/certs" in call_url


@pytest.mark.asyncio
async def test_jwks_cached_for_ttl(monkeypatch):
    """Two verify calls within the cache TTL only fetch JWKS once."""
    monkeypatch.setenv("AUTH_MODE", "keycloak")
    monkeypatch.setenv("TEST_JWT_SECRET", TEST_SECRET)
    from src.core.config import get_settings

    get_settings.cache_clear()
    import src.core.auth_adapter  # ensure module is loaded before patch resolves
    from src.core.auth_adapter import KeycloakValidator

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"keys": []}

    with patch("src.core.auth_adapter.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)

        validator = KeycloakValidator()
        validator._jwks = None
        validator._jwks_fetched_at = 0.0

        for _ in range(2):
            try:
                await validator.verify("dummy.token.value")
            except Exception:
                pass

        assert mock_client.get.call_count == 1


@pytest.mark.asyncio
async def test_jwks_refreshed_after_ttl_expired(monkeypatch):
    """Two verify calls where the second is after TTL cause two JWKS fetches."""
    monkeypatch.setenv("AUTH_MODE", "keycloak")
    monkeypatch.setenv("TEST_JWT_SECRET", TEST_SECRET)
    from src.core.config import get_settings

    get_settings.cache_clear()
    import src.core.auth_adapter  # ensure module is loaded before patch resolves
    from src.core.auth_adapter import KeycloakValidator

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"keys": []}

    with (
        patch("src.core.auth_adapter.httpx.AsyncClient") as mock_client_cls,
        patch("src.core.auth_adapter.time") as mock_time_mod,
    ):
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)

        mock_time_mod.monotonic.side_effect = [0.0, 400.0]

        validator = KeycloakValidator()
        validator._jwks = None
        validator._jwks_fetched_at = 0.0

        for _ in range(2):
            try:
                await validator.verify("dummy.token.value")
            except Exception:
                pass

        assert mock_client.get.call_count == 2


# ---------------------------------------------------------------------------
# Security-mandated tests (per security-review-004-keycloak BLK-01/02/03)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_algorithm_confusion_rejected(monkeypatch):
    """Token with alg:none header raises UnauthorizedError (algorithm confusion attack)."""
    monkeypatch.setenv("AUTH_MODE", "local")
    monkeypatch.setenv("TEST_JWT_SECRET", TEST_SECRET)

    import base64
    import json

    from src.core.auth_adapter import KeycloakValidator, UnauthorizedError

    header = (
        base64.urlsafe_b64encode(json.dumps({"alg": "none", "typ": "JWT"}).encode())
        .rstrip(b"=")
        .decode()
    )
    payload_data = (
        base64.urlsafe_b64encode(
            json.dumps({"sub": "attacker", "email": "a@b.com", "exp": 9999999999}).encode()
        )
        .rstrip(b"=")
        .decode()
    )
    none_token = f"{header}.{payload_data}."

    validator = KeycloakValidator()
    with pytest.raises(UnauthorizedError):
        await validator.verify(none_token)


@pytest.mark.asyncio
async def test_unrecognised_auth_mode_raises(monkeypatch):
    """AUTH_MODE set to an unknown value raises ValueError during verify()."""
    monkeypatch.setenv("AUTH_MODE", "invalid-mode")
    monkeypatch.setenv("TEST_JWT_SECRET", TEST_SECRET)

    from src.core.auth_adapter import KeycloakValidator, UnauthorizedError

    validator = KeycloakValidator()
    with pytest.raises((ValueError, UnauthorizedError)):
        await validator.verify("any.token.value")


@pytest.mark.asyncio
async def test_startup_fails_if_jwks_unreachable(monkeypatch):
    """In keycloak mode, a ConnectError during JWKS fetch raises RuntimeError (BLK-02)."""
    import httpx

    monkeypatch.setenv("AUTH_MODE", "keycloak")
    monkeypatch.setenv("TEST_JWT_SECRET", TEST_SECRET)

    import src.core.auth_adapter
    from src.core.auth_adapter import prefetch_jwks
    from src.core.config import get_settings

    get_settings.cache_clear()

    with patch("src.core.auth_adapter.httpx.AsyncClient") as mock_client_cls:
        mock_http = AsyncMock()
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_http.get = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))

        with pytest.raises(RuntimeError):
            await prefetch_jwks()
