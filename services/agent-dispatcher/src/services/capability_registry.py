"""Capability Registry — loads agent role definitions from registry.yaml at startup."""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

_TEMPLATE_RE = re.compile(r"^[A-Za-z0-9_\-]{0,20}\{ticket_id\}[A-Za-z0-9_\-]{0,20}$")


@dataclass
class AgentCapability:
    role_id: str
    display_name: str
    skill_file: str
    coordinator: bool
    capabilities: list[str]
    fsm_ownership: list[str]
    preferred_for: list[str]
    brainstorm_also_for: list[str]
    brainstorm_role: str


class CapabilityRegistry:
    def __init__(self, path: str) -> None:
        self._path = Path(path)
        self._agents: list[AgentCapability] = []
        self._by_role: dict[str, AgentCapability] = {}
        self._by_state: dict[str, list[AgentCapability]] = {}
        self.brainstorm_project_template: str = "df-{ticket_id}"
        self._raw_yaml: str = ""

    def load(self) -> None:
        if not self._path.exists():
            raise FileNotFoundError(f"Registry file not found: {self._path}")
        self._raw_yaml = self._path.read_text(encoding="utf-8")
        try:
            data = yaml.safe_load(self._raw_yaml)
        except yaml.YAMLError as exc:
            raise ValueError(f"Registry YAML parse error: {exc}") from exc

        if not isinstance(data, dict):
            raise ValueError("Registry YAML must be a mapping at the top level")

        template = data.get("brainstorm_project_template", "df-{ticket_id}")
        if not _TEMPLATE_RE.fullmatch(template):
            raise ValueError(
                f"Invalid brainstorm_project_template: {template!r}. "
                "Only {{ticket_id}} placeholder is allowed."
            )
        self.brainstorm_project_template = template

        agents_raw = data.get("agents", [])
        if not isinstance(agents_raw, list):
            raise ValueError("Registry 'agents' key must be a list")

        seen_ids: set[str] = set()
        agents: list[AgentCapability] = []

        for entry in agents_raw:
            role_id = entry.get("role_id", "")
            if not role_id:
                raise ValueError("Agent entry missing 'role_id'")
            if role_id in seen_ids:
                raise ValueError(f"Duplicate role_id in registry: {role_id!r}")
            seen_ids.add(role_id)

            brainstorm_role = entry.get("brainstorm_role", "contributor")
            if brainstorm_role not in ("coordinator", "contributor"):
                raise ValueError(f"Invalid brainstorm_role {brainstorm_role!r} for {role_id!r}")

            agent = AgentCapability(
                role_id=role_id,
                display_name=entry.get("display_name", role_id),
                skill_file=entry.get("skill_file", ""),
                coordinator=bool(entry.get("coordinator", False)),
                capabilities=list(entry.get("capabilities", [])),
                fsm_ownership=list(entry.get("fsm_ownership", [])),
                preferred_for=list(entry.get("preferred_for", [])),
                brainstorm_also_for=list(entry.get("brainstorm_also_for", [])),
                brainstorm_role=brainstorm_role,
            )
            agents.append(agent)

        self._agents = agents
        self._by_role = {a.role_id: a for a in agents}

        by_state: dict[str, list[AgentCapability]] = {}
        for agent in agents:
            for state in agent.fsm_ownership:
                by_state.setdefault(state, []).append(agent)
        self._by_state = by_state

        registry_hash = hashlib.sha256(self._raw_yaml.encode()).hexdigest()[:16]
        logger.info("Registry loaded: %d agents, sha256=%s", len(agents), registry_hash)

    def get_candidates_for_state(self, fsm_state: str) -> list[AgentCapability]:
        return list(self._by_state.get(fsm_state, []))

    def get_brainstorm_participants(self, fsm_state: str) -> list[AgentCapability]:
        owners = set(a.role_id for a in self._by_state.get(fsm_state, []))
        participants: list[AgentCapability] = []
        seen: set[str] = set()
        for agent in self._agents:
            if agent.role_id in owners or fsm_state in agent.brainstorm_also_for:
                if agent.role_id not in seen:
                    participants.append(agent)
                    seen.add(agent.role_id)
        return participants

    def get_by_role_id(self, role_id: str) -> AgentCapability | None:
        return self._by_role.get(role_id)

    def all_role_ids(self) -> list[str]:
        return [a.role_id for a in self._agents]

    def to_yaml_string(self) -> str:
        return self._raw_yaml

    def brainstorm_project_name(self, ticket_id: str) -> str:
        return self.brainstorm_project_template.format(ticket_id=ticket_id)


_registry: CapabilityRegistry | None = None


def get_registry() -> CapabilityRegistry:
    if _registry is None:
        raise RuntimeError("CapabilityRegistry not loaded — call load_registry() at startup")
    return _registry


def load_registry(path: str) -> CapabilityRegistry:
    global _registry
    reg = CapabilityRegistry(path)
    reg.load()
    _registry = reg
    return reg
