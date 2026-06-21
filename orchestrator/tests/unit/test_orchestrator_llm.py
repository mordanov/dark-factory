"""Unit tests for orchestrator LLM service."""
import json
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from src.schemas.schemas import TmTicket, ProjectMemoryResponse
from src.services.fsm.engine import evaluate
from src.services.llm.orchestrator_llm import _build_user_message, _parse_decision, call_orchestrator_llm
from src.core.exceptions import UpstreamError


def sample_ticket() -> TmTicket:
    return TmTicket(id="t-1", project_id="p-1", title="Feature X",
                    description="## Acceptance Criteria\n- [ ] AC1",
                    ticket_type="feature", tags=[], fsm_status="triage")


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
    mem = ProjectMemoryResponse(project_id="p-1", content="yaml: yes", version=1,
                                last_ticket_id=None, updated_at=None)
    msg = _build_user_message(ticket, ev, mem, [], {})
    assert "yaml: yes" in msg


def test_build_user_message_null_memory_note():
    ticket = sample_ticket()
    ev = sample_eval(ticket)
    msg = _build_user_message(ticket, ev, None, [], {})
    assert "null" in msg.lower() or "no project memory" in msg.lower()


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------

def test_parse_decision_advance():
    data = {
        "orchestrator_version": "1.1",
        "timestamp": "2024-01-01T00:00:00Z",
        "decision": {"action": "ADVANCE", "from_state": "triage",
                     "to_state": "specification", "assigned_agent": "project_manager",
                     "blocked_reason": None, "override_logged": False},
        "agent_briefing": {"agent_id": "project_manager", "task_summary": "Write spec",
                           "relevant_files": [], "constraints": [], "acceptance_criteria": [],
                           "context_refs": {}},
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
        "decision": {"action": "BLOCK", "from_state": "triage", "to_state": None,
                     "assigned_agent": "project_manager",
                     "blocked_reason": "Gate failed", "override_logged": False},
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
            await call_orchestrator_llm(ticket, ev, None, [], {})


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
            await call_orchestrator_llm(ticket, ev, None, [], {})
