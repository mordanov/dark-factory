"""Unit tests for credentials writing in dispatcher_service."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture()
def mock_settings(tmp_path: Path) -> MagicMock:
    s = MagicMock()
    s.agent_prompts_dir = str(tmp_path / "agents")
    s.ticket_manager_base_url = "http://ticket-manager:8000"
    return s


@pytest.fixture()
def mock_registry() -> MagicMock:
    return MagicMock()


async def test_write_credentials_creates_file(
    tmp_path: Path, mock_settings: MagicMock, mock_registry: MagicMock
) -> None:
    from src.services.dispatcher_service import _write_credentials

    mock_kc = MagicMock()
    mock_kc.get_token = AsyncMock(return_value="test-token-abc")

    with patch("src.core.keycloak_client.get_kc_client", return_value=mock_kc):
        await _write_credentials("backend", mock_settings, mock_registry)

    creds_path = Path(mock_settings.agent_prompts_dir).parent / "backend" / "credentials.json"
    assert creds_path.exists()


async def test_write_credentials_correct_keys(
    tmp_path: Path, mock_settings: MagicMock, mock_registry: MagicMock
) -> None:
    from src.services.dispatcher_service import _write_credentials

    mock_kc = MagicMock()
    mock_kc.get_token = AsyncMock(return_value="test-token-xyz")

    with (
        patch("src.core.keycloak_client.get_kc_client", return_value=mock_kc),
        patch.dict(os.environ, {"AGENT_PASSWORD_FRONTEND": "secret-pw"}),
    ):
        await _write_credentials("frontend", mock_settings, mock_registry)

    creds_path = Path(mock_settings.agent_prompts_dir).parent / "frontend" / "credentials.json"
    data = json.loads(creds_path.read_text())

    assert data["host"] == "http://ticket-manager:8000"
    assert data["token"] == "test-token-xyz"
    assert data["username"] == "frontend@agents.miveralta.ru"
    assert data["password"] == "secret-pw"


async def test_write_credentials_path_uses_role_id(
    tmp_path: Path, mock_settings: MagicMock, mock_registry: MagicMock
) -> None:
    from src.services.dispatcher_service import _write_credentials

    mock_kc = MagicMock()
    mock_kc.get_token = AsyncMock(return_value="tok")

    with patch("src.core.keycloak_client.get_kc_client", return_value=mock_kc):
        await _write_credentials("software-architect", mock_settings, mock_registry)

    creds_path = (
        Path(mock_settings.agent_prompts_dir).parent / "software-architect" / "credentials.json"
    )
    assert creds_path.exists()
    data = json.loads(creds_path.read_text())
    assert data["username"] == "software-architect@agents.miveralta.ru"


async def test_write_credentials_swallows_token_error(
    tmp_path: Path, mock_settings: MagicMock, mock_registry: MagicMock
) -> None:
    from src.services.dispatcher_service import _write_credentials

    mock_kc = MagicMock()
    mock_kc.get_token = AsyncMock(side_effect=Exception("Keycloak down"))

    with patch("src.core.keycloak_client.get_kc_client", return_value=mock_kc):
        result = await _write_credentials("backend", mock_settings, mock_registry)

    creds_path = Path(mock_settings.agent_prompts_dir).parent / "backend" / "credentials.json"
    assert not creds_path.exists()
    assert result == ""


async def test_write_credentials_rejects_traversal(
    tmp_path: Path, mock_settings: MagicMock, mock_registry: MagicMock
) -> None:
    """SEC-T01: path traversal in role_id is rejected; no file is written."""
    from src.services.dispatcher_service import _write_credentials

    mock_kc = MagicMock()
    mock_kc.get_token = AsyncMock(return_value="tok")

    with patch("src.core.keycloak_client.get_kc_client", return_value=mock_kc):
        result = await _write_credentials("../../../tmp/evil", mock_settings, mock_registry)

    assert result == ""
    evil_path = Path("/tmp/evil/credentials.json")
    assert not evil_path.exists()


async def test_write_credentials_file_permissions(
    tmp_path: Path, mock_settings: MagicMock, mock_registry: MagicMock
) -> None:
    """SEC-T07: credentials.json written with 0600 permissions."""
    from src.services.dispatcher_service import _write_credentials

    mock_kc = MagicMock()
    mock_kc.get_token = AsyncMock(return_value="tok")

    with patch("src.core.keycloak_client.get_kc_client", return_value=mock_kc):
        await _write_credentials("backend", mock_settings, mock_registry)

    creds_path = Path(mock_settings.agent_prompts_dir).parent / "backend" / "credentials.json"
    file_mode = stat.S_IMODE(os.stat(str(creds_path)).st_mode)
    assert file_mode == 0o600, f"Expected 0600, got {oct(file_mode)}"


async def test_write_credentials_returns_password_for_scrubbing(
    tmp_path: Path, mock_settings: MagicMock, mock_registry: MagicMock
) -> None:
    """The return value is the per-agent password for stdout scrubbing."""
    from src.services.dispatcher_service import _write_credentials

    mock_kc = MagicMock()
    mock_kc.get_token = AsyncMock(return_value="tok")

    with (
        patch("src.core.keycloak_client.get_kc_client", return_value=mock_kc),
        patch.dict(os.environ, {"AGENT_PASSWORD_BACKEND": "super-secret-pw"}),
    ):
        result = await _write_credentials("backend", mock_settings, mock_registry)

    assert result == "super-secret-pw"


async def test_strip_service_jwt_redacts_both_secrets() -> None:
    """SEC-T02: both JWT and per-agent password are scrubbed from stdout."""
    from src.services.dispatcher_service import _strip_service_jwt

    stdout = "some output with jwt=abc123 and password=hunter2 here"
    scrubbed = _strip_service_jwt(stdout, "abc123", "hunter2")

    assert "abc123" not in scrubbed
    assert "hunter2" not in scrubbed
    assert "[SERVICE_JWT_REDACTED]" in scrubbed
    assert "[CREDENTIAL_REDACTED]" in scrubbed
