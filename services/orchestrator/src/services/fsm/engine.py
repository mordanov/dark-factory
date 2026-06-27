"""FSM engine — pure logic, no I/O.

Defines all valid transitions, ticket-type routing, and pre-condition checks.
The engine does NOT call any external service — it only reasons about state.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.core.exceptions import FSMError
from src.schemas.schemas import TmTicket

# ---------------------------------------------------------------------------
# State definitions
# ---------------------------------------------------------------------------

TERMINAL_STATE = "done"
BLOCKED_STATE = "BLOCKED"

# Full path: feature / improvement
FULL_PATH: list[str] = [
    "backlog",
    "triage",
    "specification",
    "architecture_review",
    "implementation",
    "code_review",
    "security_review",
    "testing",
    "release",
    "done",
]

# Shortened path: bugfix
SHORT_PATH: list[str] = [
    "backlog",
    "triage",
    "specification",
    "implementation",
    "code_review",
    "security_review",
    "testing",
    "release",
    "done",
]

# Gates required to enter each state (key = to_state)
GATES_REQUIRED: dict[str, list[str]] = {
    "triage": ["triage_complete"],
    "architecture_review": [],  # assigned to software_architect, no gate yet
    "implementation": ["architecture_consistency"],  # for full path
    "code_review": [],  # agent signals implementation_finished
    "security_review": ["code_review"],
    "testing": ["security_check"],
    "release": ["test_coverage"],
    "done": [],  # devops confirms
}

# ---------------------------------------------------------------------------
# Dataclass for FSM evaluation result
# ---------------------------------------------------------------------------


@dataclass
class FSMEvaluation:
    """The FSM engine's verdict for one ticket."""

    action: str  # ADVANCE | BLOCK | WAIT | GENERATE_ADR
    from_state: str | None
    to_state: str | None
    candidate_agents: list[str]  # role IDs that own to_state (registry lookup in dispatcher)
    blocked_reason: str | None
    gates_to_evaluate: list[str]  # Gates the orchestrator LLM must evaluate
    generate_adr: bool  # True if architecture_review just passed
    context_distiller_trigger: bool
    errors: list[str]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def evaluate(ticket: TmTicket, dependency_statuses: dict[str, str]) -> FSMEvaluation:
    """Pure FSM logic — returns what action should be taken for this ticket.

    The caller (OrchestratorService) uses this to build the LLM prompt
    and interpret the LLM decision.
    """
    errors: list[str] = []
    current = ticket.fsm_status or "backlog"

    # 1. Needs-estimation gate (mandatory triage)
    if "needs-estimation" in ticket.tags and current == "backlog":
        return FSMEvaluation(
            action="WAIT",
            from_state=current,
            to_state=None,
            candidate_agents=[],
            blocked_reason="Awaiting team estimation — needs-estimation tag present",
            gates_to_evaluate=[],
            generate_adr=False,
            context_distiller_trigger=False,
            errors=errors,
        )

    # 2. Ticket type check
    ticket_type = (ticket.ticket_type or "").lower()
    if ticket_type in ("other", ""):
        return FSMEvaluation(
            action="BLOCK",
            from_state=current,
            to_state=None,
            candidate_agents=[],
            blocked_reason=f"ticket_type is '{ticket_type or 'missing'}' — triage incomplete",
            gates_to_evaluate=[],
            generate_adr=False,
            context_distiller_trigger=False,
            errors=errors,
        )

    # 3. Dependency check
    blocking_deps = [tid for tid, status in dependency_statuses.items() if status != TERMINAL_STATE]
    if blocking_deps:
        reason = "Waiting for dependencies: " + ", ".join(
            f"{tid} ({dependency_statuses[tid]})" for tid in blocking_deps
        )
        return FSMEvaluation(
            action="WAIT",
            from_state=current,
            to_state=None,
            candidate_agents=[],
            blocked_reason=reason,
            gates_to_evaluate=[],
            generate_adr=False,
            context_distiller_trigger=False,
            errors=errors,
        )

    # 4. Already done
    if current == TERMINAL_STATE:
        return FSMEvaluation(
            action="WAIT",
            from_state=current,
            to_state=None,
            candidate_agents=[],
            blocked_reason=None,
            gates_to_evaluate=[],
            generate_adr=False,
            context_distiller_trigger=False,
            errors=errors,
        )

    # 5. Determine next state from path
    path = SHORT_PATH if ticket_type == "bugfix" else FULL_PATH
    if current not in path:
        errors.append(f"Unknown fsm_status: {current}")
        current = "backlog"

    idx = path.index(current)
    if idx >= len(path) - 1:
        return FSMEvaluation(
            action="WAIT",
            from_state=current,
            to_state=None,
            candidate_agents=[],
            blocked_reason=None,
            gates_to_evaluate=[],
            generate_adr=False,
            context_distiller_trigger=True,
            errors=errors,
        )

    to_state = path[idx + 1]
    gates = list(GATES_REQUIRED.get(to_state, []))

    # For bugfix: skip architecture_consistency gate
    if ticket_type == "bugfix" and "architecture_consistency" in gates:
        gates.remove("architecture_consistency")

    generate_adr = current == "architecture_review" and ticket_type != "bugfix"
    distill_trigger = to_state == TERMINAL_STATE

    return FSMEvaluation(
        action="ADVANCE",
        from_state=current,
        to_state=to_state,
        candidate_agents=[],  # registry lookup happens in agent-dispatcher, not here
        blocked_reason=None,
        gates_to_evaluate=gates,
        generate_adr=generate_adr,
        context_distiller_trigger=distill_trigger,
        errors=errors,
    )


def validate_transition(from_state: str, to_state: str, ticket_type: str) -> None:
    """Raise FSMError if a transition is structurally invalid."""
    path = SHORT_PATH if ticket_type == "bugfix" else FULL_PATH
    if from_state not in path or to_state not in path:
        raise FSMError(f"Invalid state: {from_state!r} → {to_state!r}")
    if path.index(to_state) != path.index(from_state) + 1:
        raise FSMError(f"Non-sequential transition: {from_state!r} → {to_state!r}")
