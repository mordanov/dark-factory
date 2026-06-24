"""Context builder — assembles agent context document."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import httpx
import structlog

from src.core.config import get_settings
from src.core.keycloak_client import get_kc_client
from src.models.models import BrainstormSession
from src.schemas.schemas import AgentContext

logger = structlog.get_logger(__name__)

_METRICS_SECTION = """\
## Completion and Metrics Reporting
After completing your task:

1. Run the metrics script:
   bash development/scripts/report-task-metrics.sh \\
     --feature-name "{project_id}" \\
     --task-id "{ticket_id}" \\
     --task-description "<brief summary>" \\
     --time-spent-seconds <seconds> \\
     --tokens-spent <tokens> \\
     --model-used "<model-id>" \\
     --token-source "estimated"

2. Send a brainstorm message to project-administrator:
   payload: {{ "type": "task-metrics", "feature_name": "...", "task_id": "...",
              "task_description": "...", "time_spent_seconds": 0,
              "tokens_spent": 0, "model_used": "...", "token_source": "estimated" }}

3. End your response with a result block:

[RESULT]
{{
  "status": "completed | needs_review | blocked",
  "summary": "What was accomplished (max 500 chars)",
  "artifacts": ["relative/path/to/file.py"],
  "tm_comment": "Comment to post on the TM ticket",
  "brainstorm_consensus": null,
  "errors": []
}}
[/RESULT]
"""


async def _fetch_text(url: str, token: str) -> str:
    """Fetch text from a URL; return empty string on any error."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url, headers={"Authorization": f"Bearer {token}"})
            if resp.status_code == 200:
                data = resp.json()
                return data.get("content", "")
    except Exception as exc:
        logger.debug("Context fetch failed", url=url, error=str(exc))
    return ""


def _truncate_to_tokens(text: str, max_tokens: int) -> str:
    """Approximate token truncation by word count."""
    words = text.split()
    approx_tokens = int(len(words) * 1.3)
    if approx_tokens <= max_tokens:
        return text

    target_words = int(max_tokens / 1.3)
    truncated_words = words[:target_words]
    truncated = " ".join(truncated_words)

    last_period = truncated.rfind(". ")
    if last_period > 0:
        truncated = truncated[: last_period + 1]

    logger.warning("Project memory truncated", original_words=len(words), target_words=target_words)
    return truncated


async def build_context(
    ticket: Any,
    agent_id: str,
    brainstorm_session: BrainstormSession | None,
    previous_responses: str | None = None,
) -> tuple[str, str]:
    """Return (context_text, service_jwt).

    The JWT is returned separately so callers can strip it from agent output
    before persisting raw_output. Never store the returned JWT.
    """
    settings = get_settings()
    token = await get_kc_client().get_token()
    distiller_url = settings.context_distiller_base_url
    tm_url = settings.ticket_manager_base_url
    project_id = ticket.project_id
    ticket_id = ticket.id

    prompt_path = Path(settings.agent_prompts_dir) / f"{agent_id}.md"
    role_text = ""
    if prompt_path.exists():
        role_text = prompt_path.read_text(encoding="utf-8")

    project_memory_raw = await _fetch_text(f"{distiller_url}/memory/{project_id}", token)
    project_memory = _truncate_to_tokens(project_memory_raw, settings.context_max_tokens)

    adrs = await _fetch_text(f"{distiller_url}/memory/{project_id}/adrs", token)
    agent_config = await _fetch_text(f"{distiller_url}/memory/{project_id}/agent-config", token)

    brainstorm_section = ""
    if brainstorm_session is not None:
        brainstorm_section = (
            f"\n## Brainstorm Project\n"
            f"Project name: {brainstorm_session.project_name}\n"
            f"Round: {brainstorm_session.current_round} of {brainstorm_session.max_rounds}\n"
            f"Previous agent messages are available in the brainstorm project.\n"
        )

    previous_responses_section = ""
    if previous_responses and settings.agent_runner_mode == "api":
        previous_responses_section = f"\n## Previous Agent Responses\n{previous_responses}\n"

    metrics_section = _METRICS_SECTION.format(project_id=project_id, ticket_id=ticket_id)

    parts = [
        "# Agent Task\n",
        f"## Your Role\n{role_text}\n",
        f"## Ticket\n"
        f"- **ID**: {ticket_id}\n"
        f"- **Title**: {ticket.title}\n"
        f"- **Type**: {getattr(ticket, 'ticket_type', 'N/A')}\n"
        f"- **Project**: {project_id}\n",
        f"## Description\n{ticket.description}\n",
        f"## Your Constraints\n{agent_config}\n",
        f"## Project Context\n{project_memory}\n",
    ]

    if adrs:
        parts.append(f"## Active ADRs\n{adrs}\n")

    if brainstorm_section:
        parts.append(brainstorm_section)

    if previous_responses_section:
        parts.append(previous_responses_section)

    parts.append(
        f"## Service Token\n"
        f"Use this Bearer token for ALL API calls to Dark Factory services.\n"
        f"Token is valid for 1 hour from agent spawn time.\n\n"
        f"Authorization: Bearer {token}\n\n"
        f"TM API base: {tm_url}\n"
        f"Ticket: {ticket_id} in project {project_id}\n"
    )
    parts.append(metrics_section)

    return "\n".join(parts), token


def build_context_snapshot(ticket: Any, agent_id: str) -> dict:
    """Build context snapshot for DB storage — no secrets."""
    return {
        "ticket_id": ticket.id,
        "project_id": ticket.project_id,
        "agent_id": agent_id,
        "ticket_title": ticket.title,
        "ticket_type": getattr(ticket, "ticket_type", None),
        "description": ticket.description,
        "fsm_status": getattr(ticket, "fsm_status", None),
    }
