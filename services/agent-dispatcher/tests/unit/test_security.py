"""Unit tests for core security helpers."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from jose import JWTError, jwt


def test_create_service_token_is_valid_jwt():
    with patch("src.core.security.settings") as mock_settings:
        mock_settings.jwt_secret_key = "test-secret"
        mock_settings.jwt_algorithm = "HS256"
        mock_settings.service_jwt_expire_hours = 1

        from src.core.security import create_service_token

        token = create_service_token()

    payload = jwt.decode(token, "test-secret", algorithms=["HS256"])
    assert payload["sub"] == "service:agent-dispatcher"
    assert payload["type"] == "access"


def test_verify_access_token_returns_payload():
    secret = "test-secret"
    from datetime import UTC, datetime, timedelta

    expire = datetime.now(UTC) + timedelta(hours=1)
    token = jwt.encode(
        {"sub": "user:123", "type": "access", "exp": expire},
        secret,
        algorithm="HS256",
    )

    with patch("src.core.security.settings") as mock_settings:
        mock_settings.jwt_secret_key = secret
        mock_settings.jwt_algorithm = "HS256"

        from src.core.security import verify_access_token

        payload = verify_access_token(token)

    assert payload["sub"] == "user:123"


def test_verify_access_token_rejects_wrong_type():
    secret = "test-secret"
    from datetime import UTC, datetime, timedelta

    expire = datetime.now(UTC) + timedelta(hours=1)
    token = jwt.encode(
        {"sub": "user:123", "type": "refresh", "exp": expire},
        secret,
        algorithm="HS256",
    )

    with patch("src.core.security.settings") as mock_settings:
        mock_settings.jwt_secret_key = secret
        mock_settings.jwt_algorithm = "HS256"

        from src.core.security import verify_access_token

        with pytest.raises(JWTError):
            verify_access_token(token)


def test_verify_access_token_rejects_invalid_signature():
    secret = "test-secret"
    from datetime import UTC, datetime, timedelta

    expire = datetime.now(UTC) + timedelta(hours=1)
    token = jwt.encode(
        {"sub": "user:123", "type": "access", "exp": expire},
        "different-secret",
        algorithm="HS256",
    )

    with patch("src.core.security.settings") as mock_settings:
        mock_settings.jwt_secret_key = secret
        mock_settings.jwt_algorithm = "HS256"

        from src.core.security import verify_access_token

        with pytest.raises(JWTError):
            verify_access_token(token)
