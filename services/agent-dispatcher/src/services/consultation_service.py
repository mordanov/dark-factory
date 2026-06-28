"""Consultation service — synchronous peer consultation mediated by agent-dispatcher."""

from __future__ import annotations

import asyncio
import time
import uuid
from pathlib import Path

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.schemas.schemas import ConsultRequest, ConsultResponse
from src.services.capability_registry import get_registry
from src.services.worker_service import AgentWorkerService
from src.services.working_memory_service import WorkingMemoryService

logger = structlog.get_logger(__name__)


class ConsultationService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def consult(self, request: ConsultRequest) -> ConsultResponse:
        """Resolve a peer, forward the question, write WM entries, return answer."""
        # 1. Resolve peer by capability
        worker_svc = AgentWorkerService(self._db)
        peer = await worker_svc.resolve_capable_worker(request.required_peer_capabilities)
        if peer is None:
            raise PeerNotAvailableError(
                f"No available peer with capabilities {request.required_peer_capabilities}"
            )

        # 2. Forward question with timeout
        start = time.monotonic()
        try:
            answer = await asyncio.wait_for(
                _call_peer_agent(
                    peer.role_id,
                    request.question,
                    request.context_summary,
                ),
                timeout=request.timeout_seconds,
            )
        except TimeoutError as exc:
            raise ConsultationTimeoutError(
                f"Peer {peer.role_id!r} did not respond within {request.timeout_seconds}s"
            ) from exc
        latency_ms = int((time.monotonic() - start) * 1000)

        # 3. Write question + answer to shared working memory
        wm_svc = WorkingMemoryService(self._db)
        await wm_svc.append(
            ticket_id=request.ticket_id,
            run_id=request.run_id,
            author_role_id=request.requesting_role_id,
            entry_type="question",
            content=request.question,
            tags=["consultation"],
        )
        await wm_svc.append(
            ticket_id=request.ticket_id,
            run_id=request.run_id,
            author_role_id=peer.role_id,
            entry_type="answer",
            content=answer,
            tags=["consultation"],
        )

        import dataclasses

        return ConsultResponse(
            consultation_id=uuid.uuid4(),
            peer_role_id=peer.role_id,
            answer=answer,
            peer_capability_record=dataclasses.asdict(peer),
            latency_ms=latency_ms,
        )


async def _call_peer_agent(role_id: str, question: str, context_summary: str) -> str:
    """Invoke the peer agent runner with a targeted question prompt.

    Returns a text answer. Does not trigger FSM transitions or artifact generation.
    """
    from src.core.config import get_settings
    from src.services.runner.base import get_runner

    settings = get_settings()
    runner = get_runner()

    # Build a minimal question-only system prompt
    prompts_dir = Path(settings.agent_prompts_dir).resolve()
    skill_file = prompts_dir / f"{role_id}.md"
    if skill_file.exists():
        system_prompt = skill_file.read_text(encoding="utf-8")
    else:
        system_prompt = f"You are a specialist {role_id} agent. Answer the question concisely."

    consultation_context = f"Consultation question:\n\n{question}"
    if context_summary:
        consultation_context = f"Context: {context_summary}\n\n{consultation_context}"
    consultation_context += (
        "\n\nProvide a direct, concise expert answer. "
        "Do not include JSON result blocks — just the answer text."
    )

    _exit_code, stdout = await runner.run(
        agent_id=role_id,
        system_prompt=system_prompt,
        context=consultation_context,
        timeout_seconds=settings.agent_timeout_default,
    )
    return stdout.strip() or "(no response)"


class PeerNotAvailableError(Exception):
    pass


class ConsultationTimeoutError(Exception):
    pass
