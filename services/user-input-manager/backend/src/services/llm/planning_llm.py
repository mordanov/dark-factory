"""Planning LLM service — generates plan trees and agent configurations."""

from __future__ import annotations

import json

import structlog
from openai import AsyncOpenAI

from src.core.config import get_settings
from src.core.exceptions import UpstreamError
from src.schemas.schemas import AgentConfig, AgentOverride, PlanContent
from src.services.planning.validator import validate_plan

logger = structlog.get_logger(__name__)

PLAN_SYSTEM_PROMPT = """\
You are a senior software architect decomposing a project prompt into a structured work breakdown.

Given a refined prompt, you must produce a JSON plan with this exact structure:
{
  "epic": {
    "local_id": "epic-1",
    "title": "<concise epic title, max 200 chars>",
    "description": "<epic description, max 500 chars>",
    "ticket_type": "epic"
  },
  "stories": [
    {
      "local_id": "story-1",
      "title": "<story title, max 200 chars>",
      "description": "<story description, max 500 chars>",
      "ticket_type": "story",
      "tasks": [
        {
          "local_id": "task-1-1",
          "title": "<task title, max 200 chars>",
          "description": "<task description, max 500 chars>",
          "ticket_type": "task",
          "complexity": "S|M|L|XL",
          "depends_on": []
        }
      ]
    }
  ]
}

Rules:
- Maximum 10 stories, maximum 10 tasks per story
- local_id format: epic-1, story-N, task-N-M (N=story index, M=task index within story)
- depends_on lists local_ids of tasks WITHIN THE SAME STORY that must complete first
- No circular dependencies
- ticket_type for tasks: "task", "implementation", or "investigation"
- Respond with VALID JSON only — no markdown, no prose outside JSON
"""

AGENT_CONFIG_SYSTEM_PROMPT = """\
You are a technical project lead generating agent configuration for a Dark Factory project.

Given a project description and its work breakdown, generate per-agent override instructions.

Respond with VALID JSON only:
{
  "project_id": "<project_id>",
  "tech_stack": ["<tech1>", "<tech2>"],
  "agent_overrides": [
    {
      "agent_id": "<agent_name>",
      "override_text": "<specific instructions for this agent on this project>"
    }
  ]
}

Agent IDs to consider: backend, frontend, devops, security-architect, code-reviewer, autotester
Only include agents relevant to this project.
"""


async def generate_plan(refined_prompt: str) -> PlanContent:
    """Generate a work breakdown plan from a refined prompt. Retries once on failure."""
    settings = get_settings()
    client = AsyncOpenAI(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url or None,
        timeout=settings.openai_timeout_seconds,
    )

    for attempt in range(2):
        try:
            response = await client.chat.completions.create(
                model=settings.planning_model,
                messages=[
                    {"role": "system", "content": PLAN_SYSTEM_PROMPT},
                    {"role": "user", "content": f"Generate a plan for:\n\n{refined_prompt}"},
                ],
                temperature=0.3,
                max_tokens=4000,
                response_format={"type": "json_object"},
            )
            raw = response.choices[0].message.content or "{}"
            data = json.loads(raw)
            plan_content, errors = validate_plan(data)
            if plan_content is None:
                if attempt == 0:
                    logger.warning("Plan validation failed on attempt 1: %s", errors)
                    continue
                raise UpstreamError(f"LLM returned invalid plan: {'; '.join(errors)}")
            return plan_content
        except (json.JSONDecodeError, KeyError) as exc:
            if attempt == 0:
                logger.warning("LLM plan parse error on attempt 1: %s", exc)
                continue
            raise UpstreamError(f"LLM returned malformed plan JSON: {exc}") from exc
        except UpstreamError:
            raise
        except Exception as exc:
            if attempt == 0:
                logger.warning("LLM plan call error on attempt 1: %s", exc)
                continue
            raise UpstreamError(f"LLM service unavailable: {exc}") from exc

    raise UpstreamError("Plan generation failed after 2 attempts")


async def generate_agent_config(
    refined_prompt: str, plan: PlanContent, project_id: str
) -> AgentConfig | None:
    """Generate agent configuration. Returns None on any failure — never raises."""
    try:
        settings = get_settings()
        client = AsyncOpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url or None,
            timeout=settings.openai_timeout_seconds,
        )

        story_titles = ", ".join(s.title for s in plan.stories)
        plan_summary = f"Epic: {plan.epic.title}\nStories: {story_titles}"
        user_content = (
            f"Project ID: {project_id}\n\nPrompt:\n{refined_prompt}\n\nPlan:\n{plan_summary}"
        )

        response = await client.chat.completions.create(
            model=settings.planning_model,
            messages=[
                {"role": "system", "content": AGENT_CONFIG_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0.3,
            max_tokens=2000,
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content or "{}"
        data = json.loads(raw)
        overrides = [
            AgentOverride(agent_id=o["agent_id"], override_text=o["override_text"])
            for o in data.get("agent_overrides", [])
        ]
        return AgentConfig(
            project_id=project_id,
            tech_stack=data.get("tech_stack", []),
            agent_overrides=overrides,
        )
    except Exception as exc:
        logger.warning("Agent config generation failed (best-effort): %s", exc)
        return None
