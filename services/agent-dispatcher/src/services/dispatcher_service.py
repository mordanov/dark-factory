"""Dispatcher Service — top-level ticket lifecycle coordinator."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.core.constants import VALID_AGENT_IDS as _VALID_AGENT_IDS
from src.core.exceptions import PromptNotFoundError
from src.repositories.run_repo import AgentRunRepository
from src.schemas.schemas import AgentResult
from src.services.context_builder import build_context, build_context_snapshot
from src.services.reporter import Reporter
from src.services.result_parser import parse_result
from src.services.runner.base import get_runner

logger = structlog.get_logger(__name__)


def _resolve_prompt_path(agent_prompts_dir: str, agent_id: str) -> Path:
    """Return a safe absolute path for the agent prompt file.

    Raises PromptNotFoundError if agent_id is not whitelisted or if the
    resolved path escapes the prompts directory.
    """
    if agent_id not in _VALID_AGENT_IDS:
        raise PromptNotFoundError(f"Unknown agent_id: {agent_id!r}")
    prompts_dir = Path(agent_prompts_dir).resolve()
    prompt_path = (prompts_dir / f"{agent_id}.md").resolve()
    if not str(prompt_path).startswith(str(prompts_dir)):
        raise PromptNotFoundError(f"Path traversal detected for agent_id: {agent_id!r}")
    return prompt_path


def _strip_service_jwt(text: str, jwt_value: str) -> str:
    """Remove the service JWT from captured agent output before storage."""
    if not jwt_value:
        return text
    return text.replace(jwt_value, "[SERVICE_JWT_REDACTED]")


async def process_ticket(ticket: Any, db: AsyncSession) -> None:
    settings = get_settings()
    agent_id = ticket.assigned_agent
    ticket_id = ticket.id
    project_id = ticket.project_id

    repo = AgentRunRepository(db)
    reporter = Reporter()

    if await repo.has_running(ticket_id):
        logger.info("Skipping ticket with active run", ticket_id=ticket_id)
        return

    needs_brainstorm = getattr(ticket, "fsm_status", "") == "architecture_review" and getattr(
        ticket, "ticket_type", ""
    ) in ("feature", "improvement")

    if needs_brainstorm:
        await _run_brainstorm(ticket, db, repo, reporter, settings)
        return

    try:
        prompt_path = _resolve_prompt_path(settings.agent_prompts_dir, agent_id)
    except PromptNotFoundError as exc:
        logger.warning("Agent ID rejected", agent_id=agent_id, reason=str(exc))
        run = await repo.create(
            ticket_id=ticket_id,
            project_id=project_id,
            agent_id=agent_id,
            runner_mode=settings.agent_runner_mode,
            context_snapshot={"error": "invalid_agent_id"},
        )
        await db.commit()
        await repo.mark_failed(run.id, f"Invalid agent_id: {agent_id!r}")
        await db.commit()
        await reporter.report_result(
            ticket_id=ticket_id,
            project_id=project_id,
            result=AgentResult(
                status="needs_review",
                tm_comment=f"Invalid or unknown agent '{agent_id}'",
            ),
        )
        return

    if not prompt_path.exists():
        logger.warning("Prompt file missing", agent_id=agent_id)
        run = await repo.create(
            ticket_id=ticket_id,
            project_id=project_id,
            agent_id=agent_id,
            runner_mode=settings.agent_runner_mode,
            context_snapshot={"error": "prompt_missing"},
        )
        await db.commit()
        await repo.mark_failed(run.id, f"No prompt for agent '{agent_id}'")
        await db.commit()
        await reporter.report_result(
            ticket_id=ticket_id,
            project_id=project_id,
            result=AgentResult(
                status="needs_review",
                tm_comment=f"No prompt file found for agent '{agent_id}'",
            ),
        )
        return

    context_str, service_jwt = await build_context(ticket, agent_id, None)
    snapshot = build_context_snapshot(ticket, agent_id)
    timeout = settings.agent_timeout_for(agent_id)

    run = await repo.create(
        ticket_id=ticket_id,
        project_id=project_id,
        agent_id=agent_id,
        runner_mode=settings.agent_runner_mode,
        context_snapshot=snapshot,
    )
    await db.commit()
    await repo.mark_running(run.id)
    await db.commit()

    runner = get_runner()
    system_prompt = prompt_path.read_text(encoding="utf-8")

    try:
        exit_code, stdout = await asyncio.wait_for(
            runner.run(agent_id, system_prompt, context_str, timeout),
            timeout=timeout + 5,
        )
    except TimeoutError:
        logger.warning("Agent run timed out (outer guard)", ticket_id=ticket_id)
        await repo.mark_timed_out(run.id, "Timed out", "")
        await db.commit()
        await reporter.report_result(
            ticket_id=ticket_id,
            project_id=project_id,
            result=AgentResult(
                status="needs_review",
                tm_comment="Agent run timed out",
            ),
        )
        return

    safe_stdout = _strip_service_jwt(stdout, service_jwt)

    if exit_code != 0:
        result = parse_result(safe_stdout)
        if result.status not in ("needs_review",):
            result = AgentResult(
                status="needs_review",
                tm_comment=safe_stdout[:2000],
                errors=[f"Exit code {exit_code}"],
            )
        await repo.mark_failed(run.id, f"Exit code {exit_code}", safe_stdout)
        await db.commit()
        await reporter.report_result(
            ticket_id=ticket_id,
            project_id=project_id,
            result=result,
        )
        return

    result = parse_result(safe_stdout)

    if result.status == "completed":
        await repo.mark_done(run.id, result.model_dump(), safe_stdout)
    else:
        await repo.mark_needs_review(run.id, result.model_dump(), safe_stdout)
    await db.commit()

    await reporter.report_result(
        ticket_id=ticket_id,
        project_id=project_id,
        result=result,
    )


async def _run_brainstorm(
    ticket: Any,
    db: AsyncSession,
    repo: AgentRunRepository,
    reporter: Reporter,
    settings: Any,
) -> None:
    from src.services.brainstorm_coordinator import BrainstormCoordinator

    runner = get_runner()
    coordinator = BrainstormCoordinator(runner)
    data = await coordinator.run_brainstorm(ticket, db)
    result = aggregate_brainstorm(data)
    await reporter.report_result(
        ticket_id=ticket.id,
        project_id=ticket.project_id,
        result=result,
    )


def aggregate_brainstorm(result_data: dict) -> AgentResult:
    """Aggregate brainstorm round results into a single AgentResult."""
    agent_results: list[AgentResult] = result_data.get("agent_results", [])
    summaries = [r.summary for r in agent_results if r.summary]
    errors: list[str] = []
    for r in agent_results:
        errors.extend(r.errors)

    final_status = agent_results[-1].status if agent_results else "needs_review"
    consensus = result_data.get("consensus")
    tm_comment = "\n\n".join(r.tm_comment for r in agent_results if r.tm_comment)

    return AgentResult(
        status=final_status,
        summary="; ".join(summaries),
        tm_comment=tm_comment,
        brainstorm_consensus=consensus,
        errors=errors,
    )
