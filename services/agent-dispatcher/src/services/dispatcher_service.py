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


def _strip_service_jwt(text: str, jwt_value: str, extra_secret: str = "") -> str:
    """Remove the service JWT and any extra secret from captured agent output before storage."""
    if jwt_value:
        text = text.replace(jwt_value, "[SERVICE_JWT_REDACTED]")
    if extra_secret:
        text = text.replace(extra_secret, "[CREDENTIAL_REDACTED]")
    return text


async def process_ticket(
    ticket: Any,
    db: AsyncSession,
    required_capabilities: list[str] | None = None,
) -> None:
    from src.services.capability_registry import get_registry
    from src.services.worker_service import AgentWorkerService

    settings = get_settings()
    agent_id = ticket.assigned_agent
    ticket_id = ticket.id
    project_id = ticket.project_id

    repo = AgentRunRepository(db)
    reporter = Reporter()
    registry = get_registry()

    if await repo.has_running(ticket_id):
        logger.info("Skipping ticket with active run", ticket_id=ticket_id)
        return

    fsm_status = getattr(ticket, "fsm_status", "")
    ticket_type = getattr(ticket, "ticket_type", "")
    needs_brainstorm = fsm_status == "architecture_review" and ticket_type in (
        "feature",
        "improvement",
    )

    if needs_brainstorm:
        participants = [p.role_id for p in registry.get_brainstorm_participants(fsm_status)]
        await _run_brainstorm(
            ticket, db, repo, reporter, settings, participants=participants, registry=registry
        )
        return

    # Capability-based assignment: if required_capabilities are specified, attempt to
    # resolve the best-matched idle worker and override the statically assigned agent_id.
    matched_capability_record: dict | None = None
    matched_worker_id = None
    if required_capabilities:
        worker_svc = AgentWorkerService(db)
        matched = await worker_svc.resolve_capable_worker(required_capabilities)
        if matched:
            agent_id = matched.role_id
            import dataclasses

            matched_capability_record = dataclasses.asdict(matched)
            # Find the actual worker record ID for lifecycle tracking
            from src.repositories.worker_repository import AgentWorkerRepository

            worker_repo = AgentWorkerRepository(db)
            idle_workers = await worker_repo.get_by_role_status(matched.role_id, "idle")
            if idle_workers:
                matched_worker_id = idle_workers[0].id
                await worker_repo.update_status(matched_worker_id, "busy")
                await worker_repo.write_lifecycle_event(
                    matched_worker_id,
                    matched.role_id,
                    "assigned",
                    {"ticket_id": ticket_id},
                )
                await db.commit()
            logger.info(
                "Capability-based assignment resolved",
                required=required_capabilities,
                selected_role=agent_id,
            )
        else:
            logger.warning(
                "No capable worker found; falling back to static assignment",
                required=required_capabilities,
                static_agent_id=agent_id,
            )

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
            registry=registry,
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
            registry=registry,
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

    agent_password = await _write_credentials(agent_id, settings, registry)

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
            registry=registry,
        )
        return

    safe_stdout = _strip_service_jwt(stdout, service_jwt, agent_password)

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
            registry=registry,
        )
        return

    result = parse_result(safe_stdout)
    result.matched_capability_record = matched_capability_record

    if result.status == "completed":
        await repo.mark_done(run.id, result.model_dump(), safe_stdout)
    else:
        await repo.mark_needs_review(run.id, result.model_dump(), safe_stdout)

    if matched_worker_id is not None:
        from src.repositories.worker_repository import AgentWorkerRepository

        worker_repo = AgentWorkerRepository(db)
        await worker_repo.update_status(matched_worker_id, "idle")
        await worker_repo.write_lifecycle_event(
            matched_worker_id,
            agent_id,
            "run_completed",
            {"run_id": str(run.id), "status": result.status},
        )

    await db.commit()

    await reporter.report_result(
        ticket_id=ticket_id,
        project_id=project_id,
        result=result,
        registry=registry,
    )


async def _write_credentials(role_id: str, settings: Any, registry: Any) -> str:
    """Write credentials.json to development/{role_id}/ before agent spawn.

    Returns the per-agent password (empty string on failure) so the caller
    can redact it from captured agent stdout before storage.
    """
    import json
    import os

    from src.core.keycloak_client import get_kc_client

    # 1. Whitelist guard — same pattern as _resolve_prompt_path
    if role_id not in _VALID_AGENT_IDS:
        logger.warning("Credentials write rejected: unknown role_id %r", role_id)
        return ""

    try:
        # 2. Build and verify path stays inside development/
        dev_dir = Path(settings.agent_prompts_dir).resolve().parent
        creds_path = (dev_dir / role_id / "credentials.json").resolve()
        if not str(creds_path).startswith(str(dev_dir)):
            logger.warning("Path traversal detected for credentials, role_id=%r", role_id)
            return ""

        token = await get_kc_client().get_token()

        # 3. Per-agent password from env (backward-compat with skill files using email+password)
        env_key = f"AGENT_PASSWORD_{role_id.upper().replace('-', '_')}"
        password = os.environ.get(env_key, "")

        creds = {
            "host": settings.ticket_manager_base_url,
            "username": f"{role_id}@agents.miveralta.ru",
            "password": password,
            "token": token,
        }

        # 4. Write with restricted permissions (0600 file, 0700 dir)
        creds_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(str(creds_path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(creds, f, indent=2)

        logger.info("Credentials written for role_id=%s", role_id)
        return password
    except Exception as exc:
        logger.warning("Failed to write credentials for role_id=%r: %s", role_id, exc)
        return ""


async def _run_brainstorm(
    ticket: Any,
    db: AsyncSession,
    repo: AgentRunRepository,
    reporter: Reporter,
    settings: Any,
    participants: list[str] | None = None,
    registry: Any = None,
) -> None:
    from src.services.brainstorm_coordinator import BrainstormCoordinator

    runner = get_runner()
    coordinator = BrainstormCoordinator(runner, registry)
    data = await coordinator.run_brainstorm(ticket, db, participants=participants)
    result = aggregate_brainstorm(data)
    await reporter.report_result(
        ticket_id=ticket.id,
        project_id=ticket.project_id,
        result=result,
        registry=registry,
        brainstorm_result=data,
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
