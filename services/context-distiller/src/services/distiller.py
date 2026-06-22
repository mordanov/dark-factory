"""LLM distillation — YAML output with retry on parse failure."""

from __future__ import annotations

import json
import logging

import yaml
from openai import AsyncOpenAI

from src.core.config import get_settings
from src.core.exceptions import DistillationError, UpstreamError
from src.services.data_collector import CollectedContext

logger = logging.getLogger(__name__)

_REQUIRED_KEYS = {
    "project_id",
    "last_updated",
    "last_ticket_id",
    "architecture",
    "recent_changes",
    "open_risks",
    "known_constraints",
    "tech_stack",
}

_SYSTEM_PROMPT = """\
You are the ContextDistiller of Dark Factory.
Your task: produce an updated, compressed project memory from a completed ticket
and the existing project memory.

Rules:
- Remove outdated facts if the new ticket supersedes them.
- Keep ALL open risks, even if not resolved in this ticket.
- Note changed files by name only (no content).
- Max output: {max_tokens} tokens.
- Respond ONLY with valid YAML — no prose, no markdown fences.

Output schema (all keys required):
project_id: "..."
last_updated: "ISO8601"
last_ticket_id: "..."
architecture:
  - "..."
recent_changes:
  - ticket_id: "..."
    summary: "one sentence"
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


def _build_messages(ctx: CollectedContext, max_tokens: int) -> list[dict]:
    parts = [
        f"[COMPLETED TICKET]\n{json.dumps(ctx.ticket, indent=2, default=str)}",
        f"[AUDIT TRAIL]\n{json.dumps(ctx.audit_trail, indent=2, default=str)}",
    ]
    if ctx.current_memory:
        parts.append(f"[CURRENT PROJECT MEMORY]\n{ctx.current_memory}")
    else:
        parts.append("[CURRENT PROJECT MEMORY]\nnull — first ticket for this project")
    if ctx.adr_refs:
        parts.append(f"[ADR REFERENCES]\n{json.dumps(ctx.adr_refs, indent=2)}")
    return [
        {"role": "system", "content": _SYSTEM_PROMPT.format(max_tokens=max_tokens)},
        {"role": "user", "content": "\n\n".join(parts)},
    ]


def _validate_yaml(raw: str) -> str:
    try:
        parsed = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise ValueError(f"YAML parse error: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError("LLM output is not a YAML mapping")
    missing = _REQUIRED_KEYS - set(parsed.keys())
    if missing:
        raise ValueError(f"Missing required keys: {missing}")
    return raw


async def distill(ctx: CollectedContext) -> str:
    settings = get_settings()
    client = AsyncOpenAI(
        api_key=settings.openai_api_key,
        timeout=settings.openai_timeout_seconds,
    )
    messages = _build_messages(ctx, settings.distiller_max_memory_tokens)
    last_raw = ""
    for attempt in range(3):
        try:
            response = await client.chat.completions.create(
                model=settings.openai_model,
                messages=messages,
                temperature=0.2,
                max_tokens=settings.distiller_max_memory_tokens,
            )
        except Exception as exc:
            logger.error("LLM call failed on attempt %d: %s", attempt + 1, exc)
            raise UpstreamError(f"LLM unavailable: {exc}") from exc

        last_raw = (response.choices[0].message.content or "").strip()
        try:
            return _validate_yaml(last_raw)
        except ValueError as exc:
            logger.warning("YAML validation failed (attempt %d): %s", attempt + 1, exc)

    raise DistillationError(
        f"LLM output failed YAML validation after 3 attempts",
        raw_output=last_raw,
    )
