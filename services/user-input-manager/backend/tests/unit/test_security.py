"""Unit tests for src.core.security."""

import pytest
from jose import JWTError
from src.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_access_token,
    verify_password,
    verify_refresh_token,
)


def test_hash_and_verify_password():
    plain = "SuperSecret123!"
    hashed = hash_password(plain)
    assert hashed != plain
    assert verify_password(plain, hashed)
    assert not verify_password("wrong", hashed)


def test_access_token_roundtrip():
    token = create_access_token("user-id-123", is_admin=True)
    payload = verify_access_token(token)
    assert payload["sub"] == "user-id-123"
    assert payload["is_admin"] is True
    assert payload["type"] == "access"


def test_refresh_token_roundtrip():
    token = create_refresh_token("user-id-456")
    payload = verify_refresh_token(token)
    assert payload["sub"] == "user-id-456"
    assert payload["type"] == "refresh"


def test_access_token_rejected_as_refresh():
    token = create_access_token("x", is_admin=False)
    with pytest.raises(JWTError):
        verify_refresh_token(token)


def test_refresh_token_rejected_as_access():
    token = create_refresh_token("x")
    with pytest.raises(JWTError):
        verify_access_token(token)


def test_tampered_token_raises():
    token = create_access_token("x", is_admin=False)
    tampered = token[:-4] + "xxxx"
    with pytest.raises(JWTError):
        verify_access_token(tampered)
