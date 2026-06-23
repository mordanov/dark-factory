"""ApiRunner — executes agents via OpenAI API."""

from __future__ import annotations

import structlog
from openai import APIError, AsyncOpenAI

from src.core.config import get_settings
from src.services.runner.base import AgentRunner

logger = structlog.get_logger(__name__)


class ApiRunner(AgentRunner):
    async def run(
        self,
        agent_id: str,
        system_prompt: str,
        context: str,
        timeout_seconds: int,
    ) -> tuple[int, str]:
        settings = get_settings()
        client = AsyncOpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            timeout=float(timeout_seconds),
        )

        try:
            response = await client.chat.completions.create(
                model=settings.openai_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": context},
                ],
            )
            text = response.choices[0].message.content or ""
            return (0, text)
        except APIError as exc:
            logger.error("OpenAI API error", agent_id=agent_id, error=str(exc))
            return (-1, str(exc))
