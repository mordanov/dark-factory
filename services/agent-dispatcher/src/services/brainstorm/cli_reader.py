"""BrainstormCLIReader — reads brainstorm session messages via the brainstorm-messages CLI."""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass, field

import structlog

from src.core.exceptions import UpstreamError
from src.schemas.schemas import AgentResult

logger = structlog.get_logger(__name__)


@dataclass
class BrainstormMessage:
    author: str
    content: str
    timestamp: str


@dataclass
class BrainstormTranscript:
    project_name: str
    round_number: int
    max_rounds: int
    messages: list[BrainstormMessage]
    consensus: str  # "agreed" | "disagreed" | "inconclusive"


class BrainstormCLIReader:
    def __init__(self, npx_prefix: str, timeout_seconds: float = 30.0) -> None:
        self._prefix = npx_prefix
        self._timeout = timeout_seconds

    async def read(self, project_name: str) -> list[BrainstormMessage]:
        """Call brainstorm-messages CLI and return parsed messages.

        Returns [] if the session is empty or the project doesn't exist yet.
        Raises UpstreamError on subprocess failure or timeout.
        """
        expanded_prefix = os.path.expanduser(self._prefix)
        proc = await asyncio.create_subprocess_exec(
            "npx",
            "--prefix",
            expanded_prefix,
            "brainstorm-messages",
            project_name,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=self._timeout
            )
        except asyncio.TimeoutError:
            proc.kill()
            raise UpstreamError(
                f"brainstorm-messages timed out after {self._timeout}s"
            )

        if proc.returncode != 0:
            err = stderr.decode()[:300]
            if "no project" in err.lower() or "not found" in err.lower():
                return []
            raise UpstreamError(f"brainstorm-messages failed: {err}")

        raw = stdout.decode().strip()
        if not raw or raw == "[]":
            return []

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise UpstreamError(f"brainstorm-messages bad JSON: {exc}") from exc

        return [
            BrainstormMessage(
                author=msg.get("author", msg.get("sender", "unknown")),
                content=msg.get("content", msg.get("message", "")),
                timestamp=msg.get("timestamp", msg.get("created_at", "")),
            )
            for msg in (data if isinstance(data, list) else [])
        ]


def derive_consensus(results: list[AgentResult]) -> str:
    """Derive brainstorm consensus from agent results.

    Returns "agreed" only when every result has consensus == "agreed" (none null).
    Returns "disagreed" if any result has consensus == "disagreed".
    Returns "inconclusive" in all other cases (empty, null present, or mixed).
    """
    if not results:
        return "inconclusive"
    if any(r.brainstorm_consensus == "disagreed" for r in results):
        return "disagreed"
    if all(r.brainstorm_consensus == "agreed" for r in results):
        return "agreed"
    return "inconclusive"
