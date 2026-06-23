"""Unit tests for result_parser."""

from __future__ import annotations

import json

import pytest
from src.services.result_parser import parse_result


def make_result_block(data: dict) -> str:
    return f"Some output before\n[RESULT]\n{json.dumps(data)}\n[/RESULT]\nSome text after"


def test_valid_block_parsed_correctly():
    data = {
        "status": "completed",
        "summary": "Did the thing",
        "artifacts": ["src/foo.py"],
        "tm_comment": "Done!",
        "brainstorm_consensus": None,
        "errors": [],
    }
    result = parse_result(make_result_block(data))
    assert result.status == "completed"
    assert result.summary == "Did the thing"
    assert result.artifacts == ["src/foo.py"]
    assert result.tm_comment == "Done!"
    assert result.brainstorm_consensus is None
    assert result.errors == []


def test_missing_block_returns_needs_review():
    stdout = "A" * 3000
    result = parse_result(stdout)
    assert result.status == "needs_review"
    assert result.tm_comment == stdout[:2000]


def test_invalid_json_returns_needs_review():
    stdout = "prefix\n[RESULT]\nnot valid json\n[/RESULT]"
    result = parse_result(stdout)
    assert result.status == "needs_review"
    assert result.tm_comment == stdout[:2000]


def test_block_with_trailing_text_uses_last_block():
    data = {"status": "completed", "summary": "second", "tm_comment": "second comment"}
    stdout = (
        '[RESULT]\n{"status": "needs_review"}\n[/RESULT]\n'
        f"[RESULT]\n{json.dumps(data)}\n[/RESULT]\n"
        "trailing text"
    )
    result = parse_result(stdout)
    assert result.status == "completed"
    assert result.summary == "second"


def test_brainstorm_consensus_agreed_parsed():
    data = {
        "status": "completed",
        "summary": "agreed",
        "tm_comment": "",
        "brainstorm_consensus": "agreed",
    }
    result = parse_result(make_result_block(data))
    assert result.brainstorm_consensus == "agreed"


def test_extra_unknown_fields_ignored():
    data = {
        "status": "completed",
        "summary": "ok",
        "tm_comment": "done",
        "unknown_field": "whatever",
    }
    result = parse_result(make_result_block(data))
    assert result.status == "completed"


def test_stdout_truncated_to_2000():
    long_stdout = "x" * 5000
    result = parse_result(long_stdout)
    assert result.status == "needs_review"
    assert len(result.tm_comment) == 2000


def test_unrecognised_status_defaults_to_needs_review():
    data = {"status": "unknown_status", "summary": "test"}
    result = parse_result(make_result_block(data))
    assert result.status == "needs_review"
