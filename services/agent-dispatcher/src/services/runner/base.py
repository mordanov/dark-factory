"""AgentRunner abstract base class and factory."""

from __future__ import annotations

from abc import ABC, abstractmethod

from src.core.config import get_settings


class AgentRunner(ABC):
    @abstractmethod
    async def run(
        self,
        agent_id: str,
        system_prompt: str,
        context: str,
        timeout_seconds: int,
    ) -> tuple[int, str]:
        """Execute an agent. Returns (exit_code, stdout)."""


def get_runner() -> AgentRunner:
    settings = get_settings()
    if settings.agent_runner_mode == "api":
        from src.services.runner.api_runner import ApiRunner

        return ApiRunner()
    from src.services.runner.claude_code import ClaudeCodeRunner

    return ClaudeCodeRunner()
