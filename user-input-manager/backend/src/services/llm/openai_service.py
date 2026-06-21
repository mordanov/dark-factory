"""LLM service — prompt improvement using OpenAI.

Responsibilities (SRP):
- Build system/user messages for the refinement loop.
- Parse the structured JSON response from the model.
- Return a clean PromptRefinementResult dataclass.

The service knows nothing about HTTP, DB or ticket-manager.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from openai import AsyncOpenAI

from src.core.config import get_settings
from src.core.exceptions import UpstreamError

logger = logging.getLogger(__name__)
settings = get_settings()

SYSTEM_PROMPT = """You are an expert prompt engineer working inside a "Dark Factory" system.
Your role is to iteratively refine a user's task prompt until it is clear, complete, and actionable for a software-development team.

At each iteration you will receive:
- The original user prompt
- Any project context (existing tickets) if available
- (Optional) The history of previous refinements
- (Optional) User comments / answers to your previous questions

You must respond in VALID JSON only — no markdown, no prose outside JSON.

Response JSON schema:
{
  "refined_prompt": "<full refined prompt text>",
  "assessment": "<brief quality assessment of this version, 2-4 sentences>",
  "questions": "<clarifying questions for the user if any, or empty string>",
  "suggested_title": "<short ticket title, max 80 chars>",
  "is_ready": <true if the prompt is already high quality and ready to submit, false otherwise>
}

Refinement guidelines:
1. Make the prompt specific, measurable and unambiguous.
2. Preserve the user's original intent — never change scope without flagging it.
3. If the user answered your previous questions, incorporate the answers.
4. If you have clarifying questions, put them in "questions".
5. "is_ready" = true only when you genuinely believe no further refinement is needed.
6. Respond in the SAME LANGUAGE as the user's input.
"""


@dataclass
class RefinementResult:
    refined_prompt: str
    assessment: str
    questions: str
    suggested_title: str
    is_ready: bool


def _build_messages(
    initial_prompt: str,
    iteration_history: list[dict],
    project_context: str | None,
    user_comment: str | None,
) -> list[dict]:
    """Construct the OpenAI messages list for a refinement request."""
    parts: list[str] = []

    if project_context:
        parts.append(f"## Project Context\n{project_context}")

    parts.append(f"## Original User Prompt\n{initial_prompt}")

    if iteration_history:
        parts.append("## Previous Refinement History")
        for entry in iteration_history:
            role_label = "User" if entry["role"] == "user" else "Assistant (refined prompt)"
            parts.append(f"### {role_label} (iteration {entry['iteration_number']})\n{entry['text']}")
            if entry.get("questions"):
                parts.append(f"_Assistant questions_: {entry['questions']}")

    if user_comment:
        parts.append(f"## User's Latest Feedback / Comment\n{user_comment}")

    parts.append("## Task\nPlease provide the next refinement following the JSON schema.")

    return [{"role": "user", "content": "\n\n".join(parts)}]


async def refine_prompt(
    initial_prompt: str,
    iteration_history: list[dict],
    project_context: str | None = None,
    user_comment: str | None = None,
) -> RefinementResult:
    """Call OpenAI and return a structured refinement result.

    `iteration_history` items must have keys: role, iteration_number, text, questions (opt).
    """
    client = AsyncOpenAI(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url or None,
        timeout=settings.openai_timeout_seconds,
    )

    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + _build_messages(
        initial_prompt, iteration_history, project_context, user_comment
    )

    try:
        response = await client.chat.completions.create(
            model=settings.openai_model,
            messages=messages,
            temperature=0.4,
            max_tokens=1500,
            response_format={"type": "json_object"},
        )
    except Exception as exc:
        logger.error("OpenAI API error: %s", exc)
        raise UpstreamError(f"LLM service unavailable: {exc}") from exc

    raw = response.choices[0].message.content or "{}"

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.error("LLM returned non-JSON: %s", raw[:500])
        raise UpstreamError("LLM returned malformed response") from exc

    return RefinementResult(
        refined_prompt=data.get("refined_prompt", ""),
        assessment=data.get("assessment", ""),
        questions=data.get("questions", ""),
        suggested_title=data.get("suggested_title", "")[:500],
        is_ready=bool(data.get("is_ready", False)),
    )
