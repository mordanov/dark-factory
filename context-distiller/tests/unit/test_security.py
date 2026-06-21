"""Unit tests for JWT security module."""
import pytest
from unittest.mock import patch
from fastapi import HTTPException
from jose import jwt

from src.core.security import decode_token


def _make_token(secret="test-secret", algorithm="HS256", payload=None):
    return jwt.encode(payload or {"sub": "user-1"}, secret, algorithm=algorithm)


def test_valid_token_decoded_successfully():
    token = _make_token()
    with patch("src.core.security.get_settings") as mock_settings:
        mock_settings.return_value.jwt_secret_key = "test-secret"
        mock_settings.return_value.jwt_algorithm = "HS256"
        result = decode_token(token)
    assert result["sub"] == "user-1"


def test_invalid_token_raises_401():
    with patch("src.core.security.get_settings") as mock_settings:
        mock_settings.return_value.jwt_secret_key = "test-secret"
        mock_settings.return_value.jwt_algorithm = "HS256"
        with pytest.raises(HTTPException) as exc_info:
            decode_token("invalid.token.here")
    assert exc_info.value.status_code == 401


def test_wrong_secret_raises_401():
    token = _make_token(secret="correct-secret")
    with patch("src.core.security.get_settings") as mock_settings:
        mock_settings.return_value.jwt_secret_key = "wrong-secret"
        mock_settings.return_value.jwt_algorithm = "HS256"
        with pytest.raises(HTTPException) as exc_info:
            decode_token(token)
    assert exc_info.value.status_code == 401
