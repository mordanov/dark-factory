"""LLM Orchestrator service.

Responsibility: build the full context window for one orchestrator invocation,
call OpenAI, parse the structured JSON decision.

The FSM engine (fsm/engine.py) determines WHAT to evaluate.
This module determines HOW to call the LLM and parse the result.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timezone

from openai import AsyncOpenAI

from src.core.config import get_settings
from src.core.exceptions import UpstreamError
from src.schemas.schemas import (
    AdrSummary,
    AgentBriefing,
    DecisionDetail,
    GateResult,
    OrchestratorDecision,
    ProjectMemoryResponse,
    TmTicket,
)
from src.services.fsm.engine import FSMEvaluation

logger = logging.getLogger(__name__)
settings = get_settings()

# System prompt is long — loaded from the companion markdown file at startup.
# For the LLM call we embed it inline as a string constant here.
_SYSTEM_PROMPT = """You are the Workflow Orchestrator of Dark Factory (v1.1).
Evaluate the ticket state and return a VALID JSON decision object — no prose outside JSON.

Output schema (all fields required):
{
  "orchestrator_version": "1.1",
  "ticket_id": "<string>",
  "timestamp": "<ISO8601>",
  "decision": {
    "action": "ADVANCE | BLOCK | ASSIGN | WAIT | REQUEST_GATE | GENERATE_ADR | OVERRIDE_ACCEPTED",
    "from_state": "<string or null>",
    "to_state": "<string or null>",
    "assigned_agent": "<string or null>",
    "blocked_reason": "<string or null>",
    "override_logged": false
  },
  "agent_briefing": {
    "agent_id": "<string>",
    "task_summary": "<1-3 sentences>",
    "relevant_files": [],
    "constraints": [],
    "acceptance_criteria": [],
    "context_refs": { "project_memory_ids": [], "adr_ids": [] }
  },
  "gate_results": [],
  "adr": null,
  "dependency_check": { "all_clear": true, "blocking_dependencies": [] },
  "context_distiller_trigger": false,
  "audit_entry": { "event": "...", "actor": "orchestrator", "details": "..." },
  "errors": []
}

Rules:
- If action == BLOCK: to_state must be null, blocked_reason must be non-empty.
- If action == GENERATE_ADR: include full ADR markdown in "adr" field.
- If assigned_agent is non-null: populate agent_briefing fully.
- When in doubt about a gate: passed=false. When in doubt about action: BLOCK.
- Parse acceptance_criteria from the ## Acceptance Criteria section of ticket description.
"""


def _build_user_message(
    ticket: TmTicket,
    fsm_eval: FSMEvaluation,
    project_memory: ProjectMemoryResponse | None,
    adrs: list[AdrSummary],
    dependency_statuses: dict[str, str],
) -> str:
    parts: list[str] = []

    # --- Poll event (synthesised from FSM eval) ---
    event = {
        "event_type": "poll_tick",
        "ticket_id": ticket.id,
        "from_state": fsm_eval.from_state,
        "to_state_requested": fsm_eval.to_state,
        "agent_id": None,
        "timestamp": datetime.now(UTC).isoformat(),
        "override": ticket.override,
        "override_reason": ticket.override_reason,
        "payload": {
            "gates_to_evaluate": fsm_eval.gates_to_evaluate,
            "generate_adr": fsm_eval.generate_adr,
            "fsm_pre_evaluation": {
                "action": fsm_eval.action,
                "blocked_reason": fsm_eval.blocked_reason,
                "errors": fsm_eval.errors,
            },
        },
    }
    parts.append(f"[POLL EVENT]\n{json.dumps(event, indent=2, default=str)}")

    # --- Ticket ---
    ticket_dict = ticket.model_dump()
    parts.append(f"[TICKET]\n{json.dumps(ticket_dict, indent=2, default=str)}")

    # --- Project Memory ---
    if project_memory:
        parts.append(f"[PROJECT MEMORY]\n{project_memory.content}")
    else:
        parts.append("[PROJECT MEMORY]\nnull — no project memory available yet (new project)")

    # --- ADR List ---
    if adrs:
        adr_lines = "\n".join(
            f"- id: {a.id}\n  title: {a.title}\n  status: {a.status}\n  summary: {a.summary or ''}"
            for a in adrs
        )
        parts.append(f"[ADR LIST]\n{adr_lines}")
    else:
        parts.append("[ADR LIST]\n[]  # no ADRs yet")

    # --- Dependency statuses ---
    if dependency_statuses:
        dep_lines = "\n".join(f"  {tid}: {st}" for tid, st in dependency_statuses.items())
        parts.append(f"[DEPENDENCY STATUSES]\n{dep_lines}")

    return "\n\n".join(parts)


async def call_orchestrator_llm(
    ticket: TmTicket,
    fsm_eval: FSMEvaluation,
    project_memory: ProjectMemoryResponse | None,
    adrs: list[AdrSummary],
    dependency_statuses: dict[str, str],
) -> OrchestratorDecision:
    """Call the LLM and return a parsed OrchestratorDecision."""
    client = AsyncOpenAI(
        api_key=settings.openai_api_key,
        timeout=settings.openai_timeout_seconds,
    )
    user_msg = _build_user_message(ticket, fsm_eval, project_memory, adrs, dependency_statuses)

    try:
        response = await client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.1,
            max_tokens=2000,
            response_format={"type": "json_object"},
        )
    except Exception as exc:
        logger.error("OpenAI orchestrator call failed: %s", exc)
        raise UpstreamError(f"LLM unavailable: {exc}") from exc

    raw = response.choices[0].message.content or "{}"
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise UpstreamError("LLM returned non-JSON") from exc

    return _parse_decision(data, ticket)


def _parse_decision(data: dict, ticket: TmTicket) -> OrchestratorDecision:
    """Convert raw LLM JSON dict to typed OrchestratorDecision."""
    dec = data.get("decision", {})
    briefing_raw = data.get("agent_briefing")

    return OrchestratorDecision(
        orchestrator_version=data.get("orchestrator_version", "1.1"),
        ticket_id=ticket.id,
        timestamp=data.get("timestamp", datetime.now(UTC).isoformat()),
        decision=DecisionDetail(
            action=dec.get("action", "BLOCK"),
            from_state=dec.get("from_state"),
            to_state=dec.get("to_state"),
            assigned_agent=dec.get("assigned_agent"),
            blocked_reason=dec.get("blocked_reason"),
            override_logged=bool(dec.get("override_logged", False)),
        ),
        agent_briefing=AgentBriefing(**briefing_raw) if briefing_raw else None,
        gate_results=[
            GateResult(gate=g.get("gate", ""), passed=bool(g.get("passed")), details=g)
            for g in data.get("gate_results", [])
        ],
        adr=data.get("adr"),
        dependency_check=data.get(
            "dependency_check", {"all_clear": True, "blocking_dependencies": []}
        ),
        context_distiller_trigger=bool(data.get("context_distiller_trigger", False)),
        audit_entry=data.get("audit_entry", {}),
        errors=data.get("errors", []),
    )
