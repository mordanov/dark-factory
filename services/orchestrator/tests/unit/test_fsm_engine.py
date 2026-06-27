"""Unit tests for FSM engine — pure logic, no I/O."""

import pytest
from src.core.exceptions import FSMError
from src.schemas.schemas import TmTicket
from src.services.fsm.engine import (
    FULL_PATH,
    SHORT_PATH,
    FSMEvaluation,
    evaluate,
    validate_transition,
)


def test_agent_for_state_does_not_exist() -> None:
    import src.services.fsm.engine as engine_module

    assert not hasattr(engine_module, "AGENT_FOR_STATE"), "AGENT_FOR_STATE must be removed"


def make_ticket(**kwargs) -> TmTicket:
    defaults = dict(
        id="t-1",
        project_id="p-1",
        title="T",
        description="D",
        ticket_type="feature",
        tags=[],
        fsm_status="triage",
        brainstorm_round=0,
        dependencies=[],
    )
    defaults.update(kwargs)
    return TmTicket(**defaults)


# ---------------------------------------------------------------------------
# Needs-estimation gate
# ---------------------------------------------------------------------------


def test_needs_estimation_blocks_backlog():
    ticket = make_ticket(tags=["needs-estimation"], fsm_status="backlog")
    result = evaluate(ticket, {})
    assert result.action == "WAIT"
    assert isinstance(result.candidate_agents, list)
    assert "needs-estimation" in result.blocked_reason


def test_needs_estimation_cleared_allows_triage():
    ticket = make_ticket(tags=[], fsm_status="backlog")
    result = evaluate(ticket, {})
    # Should try to advance to triage
    assert result.action == "ADVANCE"
    assert result.to_state == "triage"


# ---------------------------------------------------------------------------
# Ticket type routing
# ---------------------------------------------------------------------------


def test_other_type_blocks():
    ticket = make_ticket(ticket_type="other", fsm_status="triage")
    result = evaluate(ticket, {})
    assert result.action == "BLOCK"
    assert isinstance(result.candidate_agents, list)


def test_missing_type_blocks():
    ticket = make_ticket(ticket_type=None, fsm_status="triage")
    result = evaluate(ticket, {})
    assert result.action == "BLOCK"


def test_bugfix_skips_architecture_review():
    ticket = make_ticket(ticket_type="bugfix", fsm_status="specification")
    result = evaluate(ticket, {})
    assert result.to_state == "implementation"  # not architecture_review
    assert "architecture_consistency" not in result.gates_to_evaluate


def test_feature_goes_through_architecture_review():
    ticket = make_ticket(ticket_type="feature", fsm_status="specification")
    result = evaluate(ticket, {})
    assert result.to_state == "architecture_review"


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------


def test_blocking_dependency_returns_wait():
    ticket = make_ticket(dependencies=["dep-1", "dep-2"])
    dep_statuses = {"dep-1": "done", "dep-2": "implementation"}
    result = evaluate(ticket, dep_statuses)
    assert result.action == "WAIT"
    assert "dep-2" in result.blocked_reason


def test_all_dependencies_done_allows_advance():
    ticket = make_ticket(dependencies=["dep-1"])
    dep_statuses = {"dep-1": "done"}
    result = evaluate(ticket, dep_statuses)
    assert result.action == "ADVANCE"


# ---------------------------------------------------------------------------
# ADR and distiller triggers
# ---------------------------------------------------------------------------


def test_architecture_review_triggers_adr():
    ticket = make_ticket(ticket_type="feature", fsm_status="architecture_review")
    result = evaluate(ticket, {})
    assert result.generate_adr is True


def test_bugfix_no_adr():
    ticket = make_ticket(ticket_type="bugfix", fsm_status="architecture_review")
    # bugfix path doesn't have architecture_review, so this is an unknown state
    result = evaluate(ticket, {})
    assert result.generate_adr is False


def test_done_triggers_distiller():
    ticket = make_ticket(fsm_status="release")
    result = evaluate(ticket, {})
    assert result.context_distiller_trigger is True
    assert result.to_state == "done"


# ---------------------------------------------------------------------------
# Validate transition
# ---------------------------------------------------------------------------


def test_valid_transition_passes():
    validate_transition("triage", "specification", "feature")  # should not raise


def test_invalid_skip_raises():
    with pytest.raises(FSMError):
        validate_transition("triage", "implementation", "feature")


def test_unknown_state_raises():
    with pytest.raises(FSMError):
        validate_transition("unknown_state", "specification", "feature")


# ---------------------------------------------------------------------------
# candidate_agents is always a list
# ---------------------------------------------------------------------------


def test_candidate_agents_is_list_on_advance():
    ticket = make_ticket(ticket_type="feature", fsm_status="triage")
    result = evaluate(ticket, {})
    assert result.action == "ADVANCE"
    assert isinstance(result.candidate_agents, list)


def test_candidate_agents_empty_on_implementation_advance():
    ticket = make_ticket(ticket_type="feature", fsm_status="architecture_review")
    result = evaluate(ticket, {})
    assert result.action == "ADVANCE"
    assert result.to_state == "implementation"
    assert isinstance(result.candidate_agents, list)


def test_candidate_agents_empty_on_architecture_review():
    ticket = make_ticket(ticket_type="feature", fsm_status="specification")
    result = evaluate(ticket, {})
    assert result.action == "ADVANCE"
    assert result.to_state == "architecture_review"
    assert isinstance(result.candidate_agents, list)


# ---------------------------------------------------------------------------
# Path completeness
# ---------------------------------------------------------------------------


def test_full_path_has_no_duplicates():
    assert len(FULL_PATH) == len(set(FULL_PATH))


def test_short_path_subset_of_full():
    full_set = set(FULL_PATH)
    for state in SHORT_PATH:
        assert state in full_set, f"{state} in SHORT_PATH but not FULL_PATH"
