"""Pure result parser — extracts [RESULT] block from agent stdout."""

from __future__ import annotations

import json
import re

import structlog

from src.schemas.schemas import AgentResult

logger = structlog.get_logger(__name__)

_RESULT_PATTERN = re.compile(r"\[RESULT\](.*?)\[/RESULT\]", re.DOTALL)


def parse_result(stdout: str) -> AgentResult:
    """Extract the last [RESULT] block from stdout. Never raises."""
    try:
        matches = _RESULT_PATTERN.findall(stdout)
        if not matches:
            logger.warning("No [RESULT] block found in agent output")
            return AgentResult(
                status="needs_review",
                tm_comment=stdout[:2000],
            )

        raw_json = matches[-1].strip()
        try:
            data = json.loads(raw_json)
        except json.JSONDecodeError:
            logger.warning("Invalid JSON in [RESULT] block")
            return AgentResult(
                status="needs_review",
                tm_comment=stdout[:2000],
            )

        known_statuses = {"completed", "needs_review", "blocked"}
        if data.get("status") not in known_statuses:
            data["status"] = "needs_review"

        try:
            return AgentResult(**data)
        except Exception:
            logger.warning("Failed to parse AgentResult from [RESULT] block")
            return AgentResult(
                status="needs_review",
                tm_comment=stdout[:2000],
            )
    except Exception:
        logger.warning("Unexpected error in result_parser")
        return AgentResult(
            status="needs_review",
            tm_comment=stdout[:2000],
        )
