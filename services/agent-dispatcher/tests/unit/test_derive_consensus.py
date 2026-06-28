"""Unit tests for derive_consensus."""

from __future__ import annotations

from src.schemas.schemas import AgentResult
from src.services.brainstorm.cli_reader import derive_consensus


def make_result(consensus: str | None) -> AgentResult:
    return AgentResult(brainstorm_consensus=consensus)


def test_all_agreed():
    results = [make_result("agreed"), make_result("agreed")]
    assert derive_consensus(results) == "agreed"


def test_any_disagreed():
    results = [make_result("agreed"), make_result("disagreed")]
    assert derive_consensus(results) == "disagreed"


def test_disagreed_wins_over_agreed():
    results = [make_result("agreed"), make_result("agreed"), make_result("disagreed")]
    assert derive_consensus(results) == "disagreed"


def test_null_consensus_is_inconclusive():
    results = [make_result(None)]
    assert derive_consensus(results) == "inconclusive"


def test_empty_results():
    assert derive_consensus([]) == "inconclusive"


def test_mixed_with_null():
    results = [make_result("agreed"), make_result(None)]
    assert derive_consensus(results) == "inconclusive"


def test_all_null():
    results = [make_result(None), make_result(None)]
    assert derive_consensus(results) == "inconclusive"


def test_single_agreed():
    assert derive_consensus([make_result("agreed")]) == "agreed"


def test_single_disagreed():
    assert derive_consensus([make_result("disagreed")]) == "disagreed"
