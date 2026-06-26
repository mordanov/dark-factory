"""Shared constants for the Agent Dispatcher service."""

from __future__ import annotations

# Whitelist of agent IDs the Dispatcher is permitted to launch.
# agent_id comes from the Orchestrator (external data) and must be validated
# before path construction to prevent directory traversal attacks.
VALID_AGENT_IDS: frozenset[str] = frozenset(
    {
        "backend",
        "frontend",
        "software-architect",
        "security-architect",
        "product-manager",
        "designer",
        "code-reviewer",
        "autotester",
        "devops",
        "project-administrator",
    }
)
