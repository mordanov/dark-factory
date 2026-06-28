"""Unit tests for BrainstormCLIReader and derive_consensus."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from src.core.exceptions import UpstreamError
from src.schemas.schemas import AgentResult
from src.services.brainstorm.cli_reader import BrainstormCLIReader, derive_consensus


def make_reader(
    prefix: str = "~/.local/share/brainstorm-mcp", timeout: float = 5.0
) -> BrainstormCLIReader:
    return BrainstormCLIReader(npx_prefix=prefix, timeout_seconds=timeout)


def make_mock_proc(returncode: int, stdout: bytes = b"", stderr: bytes = b"") -> MagicMock:
    proc = MagicMock()
    proc.returncode = returncode
    proc.communicate = AsyncMock(return_value=(stdout, stderr))
    proc.kill = MagicMock()
    return proc


# ---------------------------------------------------------------------------
# T010 — success + alias tests
# ---------------------------------------------------------------------------


async def test_read_returns_messages_on_success():
    data = [
        {
            "author": "backend",
            "content": "I suggest event sourcing.",
            "timestamp": "2026-01-01T00:00:00Z",
        }
    ]
    proc = make_mock_proc(0, stdout=json.dumps(data).encode())

    with patch("asyncio.create_subprocess_exec", return_value=proc):
        reader = make_reader()
        messages = await reader.read("df-test-ticket")

    assert len(messages) == 1
    assert messages[0].author == "backend"
    assert "event sourcing" in messages[0].content
    assert messages[0].timestamp == "2026-01-01T00:00:00Z"


async def test_read_handles_sender_alias():
    data = [
        {"sender": "frontend", "message": "I propose a SPA.", "created_at": "2026-01-01T00:00:01Z"}
    ]
    proc = make_mock_proc(0, stdout=json.dumps(data).encode())

    with patch("asyncio.create_subprocess_exec", return_value=proc):
        reader = make_reader()
        messages = await reader.read("df-test")

    assert messages[0].author == "frontend"
    assert messages[0].content == "I propose a SPA."
    assert messages[0].timestamp == "2026-01-01T00:00:01Z"


async def test_read_multiple_messages():
    data = [
        {"author": "software-architect", "content": "Use CQRS.", "timestamp": ""},
        {"author": "security-architect", "content": "Add audit log.", "timestamp": ""},
    ]
    proc = make_mock_proc(0, stdout=json.dumps(data).encode())

    with patch("asyncio.create_subprocess_exec", return_value=proc):
        messages = await make_reader().read("df-multi")

    assert len(messages) == 2
    assert messages[0].author == "software-architect"
    assert messages[1].author == "security-architect"


# ---------------------------------------------------------------------------
# T013 — empty/error/timeout tests
# ---------------------------------------------------------------------------


async def test_read_returns_empty_on_empty_stdout():
    proc = make_mock_proc(0, stdout=b"[]")

    with patch("asyncio.create_subprocess_exec", return_value=proc):
        messages = await make_reader().read("df-test-ticket")

    assert messages == []


async def test_read_returns_empty_on_blank_stdout():
    proc = make_mock_proc(0, stdout=b"")

    with patch("asyncio.create_subprocess_exec", return_value=proc):
        messages = await make_reader().read("df-test-ticket")

    assert messages == []


async def test_read_returns_empty_on_missing_project():
    proc = make_mock_proc(1, stderr=b"project not found")

    with patch("asyncio.create_subprocess_exec", return_value=proc):
        messages = await make_reader().read("df-nonexistent")

    assert messages == []


async def test_read_returns_empty_on_no_project_variant():
    proc = make_mock_proc(1, stderr=b"No project with that name found")

    with patch("asyncio.create_subprocess_exec", return_value=proc):
        messages = await make_reader().read("df-nonexistent")

    assert messages == []


async def test_read_raises_on_other_error():
    proc = make_mock_proc(1, stderr=b"unexpected internal error")

    with patch("asyncio.create_subprocess_exec", return_value=proc):
        with pytest.raises(UpstreamError, match="brainstorm-messages failed"):
            await make_reader().read("df-test")


async def test_read_raises_on_bad_json():
    proc = make_mock_proc(0, stdout=b"not-valid-json")

    with patch("asyncio.create_subprocess_exec", return_value=proc):
        with pytest.raises(UpstreamError, match="bad JSON"):
            await make_reader().read("df-test")


async def test_read_raises_on_timeout():
    proc = MagicMock()
    proc.returncode = None
    proc.communicate = AsyncMock(side_effect=TimeoutError())
    proc.kill = MagicMock()

    with patch("asyncio.create_subprocess_exec", return_value=proc):
        with pytest.raises(UpstreamError, match="timed out"):
            await make_reader(timeout=0.001).read("df-test")

    proc.kill.assert_called_once()


async def test_tilde_expanded_in_prefix(monkeypatch):
    monkeypatch.setenv("HOME", "/home/testuser")
    data = [{"author": "a", "content": "b", "timestamp": ""}]
    proc = make_mock_proc(0, stdout=json.dumps(data).encode())

    with patch("asyncio.create_subprocess_exec", return_value=proc) as mock_exec:
        reader = BrainstormCLIReader(npx_prefix="~/.local/share/brainstorm-mcp")
        await reader.read("df-test")

    call_args = mock_exec.call_args[0]
    prefix_arg = call_args[2]
    assert "~" not in prefix_arg
    assert prefix_arg.startswith("/home/testuser")
