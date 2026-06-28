"""Unit tests for src.core.security.

Note: local password auth (create_access_token, hash_password etc.) is preserved
for backward compatibility during the Keycloak migration but is no longer used
by the primary auth path. AUTH_MODE=local uses KeycloakValidator with HS256.
"""

from unittest.mock import MagicMock, patch

import pytest
from jose import JWTError


def _mock_settings():
    s = MagicMock()
    s.jwt_secret_key = "test-secret-key"
    s.jwt_algorithm = "HS256"
    s.access_token_expires_minutes = 30
    s.refresh_token_expires_days = 7
    return s


def test_hash_and_verify_password():
    from src.core.security import hash_password, verify_password

    plain = "SuperSecret123!"
    hashed = hash_password(plain)
    assert hashed != plain
    assert verify_password(plain, hashed)
    assert not verify_password("wrong", hashed)


def test_access_token_roundtrip():
    with patch("src.core.security.settings", _mock_settings()):
        from src.core.security import create_access_token, verify_access_token

        token = create_access_token("user-id-123", is_admin=True)
        payload = verify_access_token(token)
    assert payload["sub"] == "user-id-123"
    assert payload["is_admin"] is True
    assert payload["type"] == "access"


def test_refresh_token_roundtrip():
    with patch("src.core.security.settings", _mock_settings()):
        from src.core.security import create_refresh_token, verify_refresh_token

        token = create_refresh_token("user-id-456")
        payload = verify_refresh_token(token)
    assert payload["sub"] == "user-id-456"
    assert payload["type"] == "refresh"


def test_access_token_rejected_as_refresh():
    with patch("src.core.security.settings", _mock_settings()):
        from src.core.security import create_access_token, verify_refresh_token

        token = create_access_token("x", is_admin=False)
        with pytest.raises(JWTError):
            verify_refresh_token(token)


def test_refresh_token_rejected_as_access():
    with patch("src.core.security.settings", _mock_settings()):
        from src.core.security import create_refresh_token, verify_access_token

        token = create_refresh_token("x")
        with pytest.raises(JWTError):
            verify_access_token(token)


def test_tampered_token_raises():
    with patch("src.core.security.settings", _mock_settings()):
        from src.core.security import create_access_token, verify_access_token

        token = create_access_token("x", is_admin=False)
        tampered = token[:-4] + "xxxx"
        with pytest.raises(JWTError):
            verify_access_token(tampered)
