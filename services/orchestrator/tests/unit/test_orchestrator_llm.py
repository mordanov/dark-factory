"""Unit tests for orchestrator LLM service."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from src.core.exceptions import UpstreamError
from src.schemas.schemas import ProjectMemoryResponse, TmTicket
from src.services.fsm.engine import evaluate
from src.services.llm.orchestrator_llm import (
    _build_user_message,
    _parse_decision,
    call_orchestrator_llm,
)


def sample_ticket() -> TmTicket:
    return TmTicket(
        id="t-1",
        project_id="p-1",
        title="Feature X",
        description="## Acceptance Criteria\n- [ ] AC1",
        ticket_type="feature",
        tags=[],
        fsm_status="triage",
    )


def sample_eval(ticket):
    return evaluate(ticket, {})


# ---------------------------------------------------------------------------
# Message building
# ---------------------------------------------------------------------------


def test_build_user_message_contains_ticket_id():
    ticket = sample_ticket()
    ev = sample_eval(ticket)
    msg = _build_user_message(ticket, ev, None, [], {})
    assert "t-1" in msg


def test_build_user_message_includes_poll_event():
    ticket = sample_ticket()
    ev = sample_eval(ticket)
    msg = _build_user_message(ticket, ev, None, [], {})
    assert "[POLL EVENT]" in msg
    assert "[TICKET]" in msg


def test_build_user_message_with_memory():
    ticket = sample_ticket()
    ev = sample_eval(ticket)
    mem = ProjectMemoryResponse(
        project_id="p-1", content="yaml: yes", version=1, last_ticket_id=None, updated_at=None
    )
    msg = _build_user_message(ticket, ev, mem, [], {})
    assert "yaml: yes" in msg


def test_build_user_message_null_memory_note():
    ticket = sample_ticket()
    ev = sample_eval(ticket)
    msg = _build_user_message(ticket, ev, None, [], {})
    assert "null" in msg.lower() or "no project memory" in msg.lower()


def test_build_user_message_includes_registry_section():
    ticket = sample_ticket()
    ev = sample_eval(ticket)
    registry_yaml = (
        "version: '1.0'\nbrainstorm_project_template: 'df-{ticket_id}'\nagents:\n"
        "  - role_id: backend\n    display_name: Backend\n    skill_file: b.md\n"
        "    capabilities: [python_backend]\n    fsm_ownership: [implementation]\n"
        "    preferred_for: []\n    brainstorm_also_for: []\n    brainstorm_role: contributor\n"
    )
    msg = _build_user_message(
        ticket, ev, None, [], {}, job_payload={"registry_yaml": registry_yaml}
    )
    assert "[AGENT REGISTRY]" in msg
    assert "backend" in msg


def test_build_user_message_no_registry_section_when_empty():
    ticket = sample_ticket()
    ev = sample_eval(ticket)
    msg = _build_user_message(ticket, ev, None, [], {}, job_payload={})
    assert "[AGENT REGISTRY]" not in msg


# ---------------------------------------------------------------------------
# SEC-T10: system prompt contains injection-hardening instructions
# ---------------------------------------------------------------------------


def test_system_prompt_contains_injection_hardening():
    from src.services.llm.orchestrator_llm import _SYSTEM_PROMPT

    assert "user-supplied" in _SYSTEM_PROMPT.lower(), (
        "System prompt must note that [TICKET] section is user-supplied content"
    )
    assert "reference data" in _SYSTEM_PROMPT.lower(), (
        "System prompt must note that [AGENT REGISTRY] section is reference data"
    )


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------


def test_parse_decision_advance():
    data = {
        "orchestrator_version": "1.1",
        "timestamp": "2024-01-01T00:00:00Z",
        "decision": {
            "action": "ADVANCE",
            "from_state": "triage",
            "to_state": "specification",
            "assigned_agent": "project_manager",
            "blocked_reason": None,
            "override_logged": False,
        },
        "agent_briefing": {
            "agent_id": "project_manager",
            "task_summary": "Write spec",
            "relevant_files": [],
            "constraints": [],
            "acceptance_criteria": [],
            "context_refs": {},
        },
        "gate_results": [],
        "adr": None,
        "dependency_check": {"all_clear": True, "blocking_dependencies": []},
        "context_distiller_trigger": False,
        "audit_entry": {"event": "ADVANCE", "actor": "orchestrator", "details": "ok"},
        "errors": [],
    }
    ticket = sample_ticket()
    decision = _parse_decision(data, ticket)
    assert decision.decision.action == "ADVANCE"
    assert decision.decision.to_state == "specification"
    assert decision.agent_briefing.agent_id == "project_manager"


def test_parse_decision_block():
    data = {
        "orchestrator_version": "1.1",
        "timestamp": "2024-01-01T00:00:00Z",
        "decision": {
            "action": "BLOCK",
            "from_state": "triage",
            "to_state": None,
            "assigned_agent": "project_manager",
            "blocked_reason": "Gate failed",
            "override_logged": False,
        },
        "agent_briefing": None,
        "gate_results": [{"gate": "code_review", "passed": False, "critical_issues": ["X"]}],
        "adr": None,
        "dependency_check": {"all_clear": True, "blocking_dependencies": []},
        "context_distiller_trigger": False,
        "audit_entry": {"event": "BLOCK", "actor": "orchestrator", "details": "blocked"},
        "errors": [],
    }
    ticket = sample_ticket()
    decision = _parse_decision(data, ticket)
    assert decision.decision.action == "BLOCK"
    assert decision.decision.to_state is None
    assert len(decision.gate_results) == 1
    assert not decision.gate_results[0].passed


# ---------------------------------------------------------------------------
# LLM call — error handling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_call_orchestrator_llm_api_error():
    ticket = sample_ticket()
    ev = sample_eval(ticket)
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(side_effect=Exception("timeout"))

    with patch("src.services.llm.orchestrator_llm.AsyncOpenAI", return_value=mock_client):
        with pytest.raises(UpstreamError, match="LLM unavailable"):
            await call_orchestrator_llm(ticket, ev, None, [], {}, job_payload={})


@pytest.mark.asyncio
async def test_call_orchestrator_llm_bad_json():
    ticket = sample_ticket()
    ev = sample_eval(ticket)
    mock_choice = MagicMock()
    mock_choice.message.content = "not valid json {{{"
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    with patch("src.services.llm.orchestrator_llm.AsyncOpenAI", return_value=mock_client):
        with pytest.raises(UpstreamError, match="non-JSON"):
            await call_orchestrator_llm(ticket, ev, None, [], {}, job_payload={})


# ---------------------------------------------------------------------------
# T020 — Brainstorm Transcript section tests
# ---------------------------------------------------------------------------


def make_arch_ticket() -> TmTicket:
    return TmTicket(
        id="t-arch",
        project_id="p-1",
        title="Architecture Review",
        description="## Acceptance Criteria\n- [ ] arch AC1",
        ticket_type="feature",
        tags=[],
        fsm_status="architecture_review",
    )


def test_transcript_section_rendered():
    ticket = make_arch_ticket()
    ev = sample_eval(ticket)
    payload = {
        "brainstorm_transcript": {
            "project_name": "df-t1",
            "round_number": 1,
            "max_rounds": 3,
            "consensus": "inconclusive",
            "messages": [
                {"author": "software-architect", "content": "Use event sourcing.", "timestamp": ""},
                {
                    "author": "security-architect",
                    "content": "Agreed but add audit log.",
                    "timestamp": "",
                },
            ],
        }
    }
    msg = _build_user_message(ticket, ev, None, [], {}, job_payload=payload)

    assert "[BRAINSTORM TRANSCRIPT]" in msg
    assert "software-architect" in msg
    assert "Use event sourcing" in msg
    assert "security-architect" in msg
    assert "add audit log" in msg
    assert "Round: 1 of 3" in msg
    assert "inconclusive" in msg
    assert "df-t1" in msg


def test_transcript_section_no_messages_shows_placeholder():
    ticket = make_arch_ticket()
    ev = sample_eval(ticket)
    payload = {
        "brainstorm_transcript": {
            "project_name": "df-t1",
            "round_number": 1,
            "max_rounds": 3,
            "consensus": "inconclusive",
            "messages": [],
        }
    }
    msg = _build_user_message(ticket, ev, None, [], {}, job_payload=payload)

    assert "[BRAINSTORM TRANSCRIPT]" in msg
    assert "(no messages)" in msg


def test_no_transcript_for_arch_review_shows_wait_hint():
    ticket = make_arch_ticket()
    ev = sample_eval(ticket)
    msg = _build_user_message(ticket, ev, None, [], {}, job_payload={})

    assert "[BRAINSTORM TRANSCRIPT]" in msg
    assert "WAIT" in msg or "No transcript" in msg


def test_no_transcript_for_other_states_no_section():
    ticket = sample_ticket()  # fsm_status="triage"
    ev = sample_eval(ticket)
    msg = _build_user_message(ticket, ev, None, [], {}, job_payload={})

    assert "[BRAINSTORM TRANSCRIPT]" not in msg
