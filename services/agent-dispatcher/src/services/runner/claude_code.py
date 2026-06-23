"""ClaudeCodeRunner — executes agents via asyncio subprocess."""

from __future__ import annotations

import asyncio

import structlog

from src.core.config import get_settings
from src.services.runner.base import AgentRunner

logger = structlog.get_logger(__name__)


class ClaudeCodeRunner(AgentRunner):
    async def run(
        self,
        agent_id: str,
        system_prompt: str,
        context: str,
        timeout_seconds: int,
    ) -> tuple[int, str]:
        settings = get_settings()
        claude_path = settings.claude_code_path
        mcp_config = settings.claude_mcp_config_path

        cmd = [
            claude_path,
            "--print",
            "--mcp-config",
            mcp_config,
            "--system-prompt",
            system_prompt,
            context,
        ]

        captured = ""
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            try:
                stdout_bytes, _ = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout_seconds
                )
                captured = stdout_bytes.decode("utf-8", errors="replace") if stdout_bytes else ""
                return (proc.returncode or 0, captured)
            except TimeoutError:
                logger.warning("Agent subprocess timed out", agent_id=agent_id)
                proc.kill()
                try:
                    stdout_bytes, _ = await proc.communicate()
                    captured = (
                        stdout_bytes.decode("utf-8", errors="replace") if stdout_bytes else ""
                    )
                except Exception:
                    pass
                return (-1, captured)
        except OSError as exc:
            logger.error("Failed to start agent subprocess", agent_id=agent_id, error=str(exc))
            return (-1, str(exc))
