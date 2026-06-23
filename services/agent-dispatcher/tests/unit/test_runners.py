"""Unit tests for agent runners (mocked subprocess and OpenAI)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


async def test_claude_code_runner_success():
    with patch("asyncio.create_subprocess_exec") as mock_exec:
        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"[RESULT]\n{}\n[/RESULT]", b""))
        mock_exec.return_value = mock_proc

        with patch("src.services.runner.claude_code.get_settings") as mock_settings:
            settings = MagicMock()
            settings.claude_code_path = "claude"
            settings.claude_mcp_config_path = "~/.claude/mcp_config.json"
            mock_settings.return_value = settings

            from src.services.runner.claude_code import ClaudeCodeRunner

            runner = ClaudeCodeRunner()
            exit_code, output = await runner.run("backend", "system prompt", "context", 300)

    assert exit_code == 0
    assert "[RESULT]" in output


async def test_claude_code_runner_timeout_kills_subprocess():
    with patch("asyncio.create_subprocess_exec") as mock_exec:
        mock_proc = AsyncMock()
        mock_proc.returncode = -1
        mock_proc.kill = MagicMock()

        async def slow_communicate():
            await asyncio.sleep(1000)
            return b"partial", b""

        mock_proc.communicate = AsyncMock(side_effect=[TimeoutError(), (b"partial", b"")])
        mock_exec.return_value = mock_proc

        with patch("src.services.runner.claude_code.get_settings") as mock_settings:
            settings = MagicMock()
            settings.claude_code_path = "claude"
            settings.claude_mcp_config_path = "~/.claude/mcp_config.json"
            mock_settings.return_value = settings

            with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError):
                from src.services.runner.claude_code import ClaudeCodeRunner

                runner = ClaudeCodeRunner()
                exit_code, output = await runner.run("backend", "sys", "ctx", 1)

    assert exit_code == -1


async def test_claude_code_runner_oserror_returns_minus_one():
    with patch("asyncio.create_subprocess_exec", side_effect=OSError("no such file")):
        with patch("src.services.runner.claude_code.get_settings") as mock_settings:
            settings = MagicMock()
            settings.claude_code_path = "nonexistent_claude"
            settings.claude_mcp_config_path = "~/.claude/mcp_config.json"
            mock_settings.return_value = settings

            from src.services.runner.claude_code import ClaudeCodeRunner

            runner = ClaudeCodeRunner()
            exit_code, output = await runner.run("backend", "sys", "ctx", 300)

    assert exit_code == -1
    assert "no such file" in output


async def test_api_runner_success():
    with patch("src.services.runner.api_runner.AsyncOpenAI") as mock_openai_cls:
        mock_client = AsyncMock()
        mock_choice = MagicMock()
        mock_choice.message.content = "response text"
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        mock_openai_cls.return_value = mock_client

        with patch("src.services.runner.api_runner.get_settings") as mock_settings:
            settings = MagicMock()
            settings.openai_api_key = "test-key"
            settings.openai_model = "gpt-4o"
            mock_settings.return_value = settings

            from src.services.runner.api_runner import ApiRunner

            runner = ApiRunner()
            exit_code, output = await runner.run("backend", "sys", "ctx", 300)

    assert exit_code == 0
    assert output == "response text"


async def test_api_runner_api_error_returns_minus_one():
    from openai import APIError

    with patch("src.services.runner.api_runner.AsyncOpenAI") as mock_openai_cls:
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=APIError("API error", request=MagicMock(), body=None)
        )
        mock_openai_cls.return_value = mock_client

        with patch("src.services.runner.api_runner.get_settings") as mock_settings:
            settings = MagicMock()
            settings.openai_api_key = "test-key"
            settings.openai_model = "gpt-4o"
            mock_settings.return_value = settings

            from src.services.runner.api_runner import ApiRunner

            runner = ApiRunner()
            exit_code, output = await runner.run("backend", "sys", "ctx", 300)

    assert exit_code == -1
    assert "API error" in output
