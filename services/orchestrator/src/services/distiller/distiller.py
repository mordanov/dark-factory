"""ContextDistiller — compresses a closed ticket into project memory."""

from __future__ import annotations

import json
import logging

from openai import AsyncOpenAI

from src.core.config import get_settings
from src.core.exceptions import UpstreamError
from src.schemas.schemas import TmTicket

logger = logging.getLogger(__name__)
settings = get_settings()

_SYSTEM_PROMPT = """You are the ContextDistiller of Dark Factory.
Your task: produce an updated, compressed project memory from a completed ticket
and the existing project memory.

Rules:
- Remove outdated facts if the new ticket supersedes them.
- Keep all open risks, even if not resolved.
- Note changed files by name only (no content).
- Max output: 2000 tokens.
- Respond ONLY with valid YAML — no prose, no markdown fences.

Output schema:
project_id: "..."
last_updated: "ISO8601"
last_ticket_id: "..."
architecture:
  - "..."
recent_changes:
  - ticket_id: "..."
    summary: "..."
    files_changed: []
    risks: []
open_risks:
  - "..."
known_constraints:
  - "..."
tech_stack:
  backend: "..."
  frontend: "..."
  database: "..."
  infra: "..."
"""


async def distill(
    ticket: TmTicket,
    audit_trail: list[dict],
    current_memory: str | None,
) -> str:
    """Call LLM and return updated project_memory YAML string."""
    client = AsyncOpenAI(
        api_key=settings.openai_api_key,
        timeout=settings.openai_timeout_seconds,
    )

    parts = [
        f"[COMPLETED TICKET]\n{json.dumps(ticket.model_dump(), indent=2, default=str)}",
        f"[AUDIT TRAIL]\n{json.dumps(audit_trail, indent=2, default=str)}",
    ]
    if current_memory:
        parts.append(f"[CURRENT PROJECT MEMORY]\n{current_memory}")
    else:
        parts.append("[CURRENT PROJECT MEMORY]\nnull — first ticket for this project")

    user_msg = "\n\n".join(parts)

    try:
        response = await client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.2,
            max_tokens=settings.distiller_max_memory_tokens,
        )
    except Exception as exc:
        logger.error("ContextDistiller LLM error: %s", exc)
        raise UpstreamError(f"Distiller LLM unavailable: {exc}") from exc

    return response.choices[0].message.content or ""
