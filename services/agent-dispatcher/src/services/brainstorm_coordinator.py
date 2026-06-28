"""BrainstormCoordinator — multi-round sequential session manager."""

from __future__ import annotations

from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.core.exceptions import PromptNotFoundError, UpstreamError
from src.repositories.brainstorm_repo import BrainstormSessionRepository
from src.repositories.run_repo import AgentRunRepository
from src.schemas.schemas import AgentResult
from src.services.brainstorm.cli_reader import (
    BrainstormCLIReader,
    BrainstormTranscript,
    derive_consensus,
)
from src.services.capability_registry import CapabilityRegistry
from src.services.context_builder import build_context, build_context_snapshot
from src.services.dispatcher_service import _resolve_prompt_path, _strip_service_jwt
from src.services.result_parser import parse_result
from src.services.runner.base import AgentRunner

logger = structlog.get_logger(__name__)


class BrainstormCoordinator:
    def __init__(self, runner: AgentRunner, registry: CapabilityRegistry) -> None:
        self._runner = runner
        self._registry = registry

    async def run_brainstorm(
        self,
        ticket: Any,
        db: AsyncSession,
        participants: list[str] | None = None,
    ) -> dict:
        settings = get_settings()
        bs_repo = BrainstormSessionRepository(db)
        run_repo = AgentRunRepository(db)

        session = await bs_repo.get_or_create(ticket.id, max_rounds=settings.brainstorm_max_rounds)
        await db.flush()

        agents = participants if participants is not None else settings.brainstorm_agents_list
        max_rounds = settings.brainstorm_max_rounds
        agent_results: list[AgentResult] = []
        concluded = False
        consensus: str | None = None
        previous_tm_comment: str | None = None

        for round_num in range(1, max_rounds + 1):
            for agent_id in agents:
                try:
                    prompt_path = _resolve_prompt_path(settings.agent_prompts_dir, agent_id)
                except PromptNotFoundError as exc:
                    logger.warning(
                        "Brainstorm agent ID rejected", agent_id=agent_id, reason=str(exc)
                    )
                    agent_results.append(
                        AgentResult(
                            status="needs_review",
                            tm_comment=f"Invalid agent_id in brainstorm config: {agent_id!r}",
                        )
                    )
                    continue

                if not prompt_path.exists():
                    logger.warning("Brainstorm prompt missing", agent_id=agent_id)
                    agent_results.append(
                        AgentResult(
                            status="needs_review",
                            tm_comment=f"Prompt missing for {agent_id}",
                        )
                    )
                    continue

                system_prompt = prompt_path.read_text(encoding="utf-8")
                context_str, service_jwt = await build_context(
                    ticket,
                    agent_id,
                    session,
                    previous_responses=previous_tm_comment,
                )
                snapshot = build_context_snapshot(ticket, agent_id)
                timeout = settings.agent_timeout_for(agent_id)

                run = await run_repo.create(
                    ticket_id=ticket.id,
                    project_id=ticket.project_id,
                    agent_id=agent_id,
                    runner_mode=settings.agent_runner_mode,
                    context_snapshot=snapshot,
                    round_number=round_num,
                    brainstorm_session_id=session.id,
                )
                await db.flush()
                await run_repo.mark_running(run.id)
                await db.flush()

                exit_code, stdout = await self._runner.run(
                    agent_id, system_prompt, context_str, timeout
                )

                safe_stdout = _strip_service_jwt(stdout, service_jwt)
                result = parse_result(safe_stdout)
                agent_results.append(result)
                previous_tm_comment = result.tm_comment

                if exit_code == 0 and result.status == "completed":
                    await run_repo.mark_done(run.id, result.model_dump(), safe_stdout)
                else:
                    await run_repo.mark_needs_review(run.id, result.model_dump(), safe_stdout)
                await db.flush()

                if result.brainstorm_consensus == "agreed":
                    consensus = "agreed"
                    await bs_repo.conclude(session.id, "agreed")
                    await db.flush()
                    concluded = True
                    break

            if concluded:
                break

            await bs_repo.increment_round(session.id)
            await db.flush()

        if not concluded:
            await bs_repo.conclude(session.id, "disagreed")
            await db.flush()

        project_name = self._registry.brainstorm_project_name(ticket.id)
        reader = BrainstormCLIReader(
            npx_prefix=settings.brainstorm_npx_prefix,
            timeout_seconds=settings.brainstorm_cli_timeout_seconds,
        )
        try:
            messages = await reader.read(project_name)
            logger.info(
                "Brainstorm session read",
                project_name=project_name,
                round=round_num,
                message_count=len(messages),
            )
        except UpstreamError as exc:
            logger.warning("Could not read brainstorm session", error=str(exc))
            messages = []

        consensus_str = derive_consensus(agent_results)
        transcript = BrainstormTranscript(
            project_name=project_name,
            round_number=round_num,
            max_rounds=max_rounds,
            messages=messages,
            consensus=consensus_str,
        )

        return {
            "concluded": True,
            "consensus": consensus,
            "rounds_completed": round_num,
            "agent_results": agent_results,
            "transcript": transcript,
        }
