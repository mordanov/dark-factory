"""Unit tests for CapabilityRegistry."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from src.services.capability_registry import (
    AgentCapability,
    CapabilityRegistry,
    get_registry,
    load_registry,
)


MINIMAL_YAML = textwrap.dedent(
    """\
    version: "1.0"
    brainstorm_project_template: "df-{ticket_id}"
    agents:
      - role_id: backend
        display_name: Backend Developer Python
        skill_file: backend-developer-python.md
        coordinator: false
        capabilities:
          - python_backend
          - fastapi
        fsm_ownership:
          - implementation
        preferred_for:
          - python
        brainstorm_also_for: []
        brainstorm_role: contributor
      - role_id: frontend
        display_name: Frontend Developer React
        skill_file: frontend-developer-react.md
        coordinator: false
        capabilities:
          - react
          - typescript
        fsm_ownership:
          - implementation
        preferred_for:
          - react
        brainstorm_also_for: []
        brainstorm_role: contributor
      - role_id: software-architect
        display_name: Software Architect
        skill_file: software-architect.md
        coordinator: true
        capabilities:
          - system_design
        fsm_ownership:
          - architecture_review
        preferred_for:
          - architecture
        brainstorm_also_for: []
        brainstorm_role: coordinator
      - role_id: security-architect
        display_name: Security Architect
        skill_file: security-architect.md
        coordinator: false
        capabilities:
          - threat_modeling
        fsm_ownership:
          - security_review
        preferred_for:
          - security
        brainstorm_also_for:
          - architecture_review
        brainstorm_role: contributor
    """
)


@pytest.fixture()
def registry_file(tmp_path: Path) -> Path:
    f = tmp_path / "registry.yaml"
    f.write_text(MINIMAL_YAML, encoding="utf-8")
    return f


def _load(path: Path) -> CapabilityRegistry:
    reg = CapabilityRegistry(str(path))
    reg.load()
    return reg


# ---------------------------------------------------------------------------
# Load succeeds
# ---------------------------------------------------------------------------


def test_load_succeeds(registry_file: Path) -> None:
    reg = _load(registry_file)
    assert len(reg.all_role_ids()) == 4


# ---------------------------------------------------------------------------
# Candidates for implementation state
# ---------------------------------------------------------------------------


def test_candidates_for_implementation(registry_file: Path) -> None:
    reg = _load(registry_file)
    candidates = reg.get_candidates_for_state("implementation")
    ids = [c.role_id for c in candidates]
    assert "backend" in ids
    assert "frontend" in ids


# ---------------------------------------------------------------------------
# Unknown state returns empty list
# ---------------------------------------------------------------------------


def test_unknown_state_returns_empty(registry_file: Path) -> None:
    reg = _load(registry_file)
    assert reg.get_candidates_for_state("nonexistent_state") == []


# ---------------------------------------------------------------------------
# Brainstorm participants includes also_for
# ---------------------------------------------------------------------------


def test_get_brainstorm_participants_architecture_review_includes_security(
    registry_file: Path,
) -> None:
    reg = _load(registry_file)
    participants = reg.get_brainstorm_participants("architecture_review")
    ids = [p.role_id for p in participants]
    assert "software-architect" in ids
    assert "security-architect" in ids


def test_get_brainstorm_participants_single_owner_no_also_for(registry_file: Path) -> None:
    reg = _load(registry_file)
    participants = reg.get_brainstorm_participants("security_review")
    ids = [p.role_id for p in participants]
    assert ids == ["security-architect"]


# ---------------------------------------------------------------------------
# get_by_role_id found / not found
# ---------------------------------------------------------------------------


def test_get_by_role_id_found(registry_file: Path) -> None:
    reg = _load(registry_file)
    agent = reg.get_by_role_id("backend")
    assert agent is not None
    assert agent.role_id == "backend"
    assert "python_backend" in agent.capabilities


def test_get_by_role_id_not_found(registry_file: Path) -> None:
    reg = _load(registry_file)
    assert reg.get_by_role_id("nonexistent") is None


# ---------------------------------------------------------------------------
# brainstorm_project_name
# ---------------------------------------------------------------------------


def test_brainstorm_project_name(registry_file: Path) -> None:
    reg = _load(registry_file)
    assert reg.brainstorm_project_name("TKT-42") == "df-TKT-42"


# ---------------------------------------------------------------------------
# to_yaml_string valid
# ---------------------------------------------------------------------------


def test_to_yaml_string_valid(registry_file: Path) -> None:
    reg = _load(registry_file)
    raw = reg.to_yaml_string()
    assert "backend" in raw
    assert "brainstorm_project_template" in raw


# ---------------------------------------------------------------------------
# Missing file raises FileNotFoundError
# ---------------------------------------------------------------------------


def test_load_missing_file(tmp_path: Path) -> None:
    reg = CapabilityRegistry(str(tmp_path / "missing.yaml"))
    with pytest.raises(FileNotFoundError):
        reg.load()


# ---------------------------------------------------------------------------
# Malformed YAML raises ValueError
# ---------------------------------------------------------------------------


def test_load_invalid_yaml(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("agents: [unclosed", encoding="utf-8")
    reg = CapabilityRegistry(str(bad))
    with pytest.raises(ValueError):
        reg.load()


# ---------------------------------------------------------------------------
# Duplicate role_id raises ValueError
# ---------------------------------------------------------------------------


def test_load_duplicate_role_id(tmp_path: Path) -> None:
    dup = tmp_path / "dup.yaml"
    dup.write_text(
        "version: '1.0'\nbrainstorm_project_template: 'df-{ticket_id}'\nagents:\n"
        "  - role_id: backend\n    display_name: A\n    skill_file: a.md\n"
        "    brainstorm_role: contributor\n"
        "  - role_id: backend\n    display_name: B\n    skill_file: b.md\n"
        "    brainstorm_role: contributor\n",
        encoding="utf-8",
    )
    reg = CapabilityRegistry(str(dup))
    with pytest.raises(ValueError, match="Duplicate"):
        reg.load()


# ---------------------------------------------------------------------------
# Non-dict top-level raises ValueError (line 43)
# ---------------------------------------------------------------------------


def test_load_non_dict_yaml(tmp_path: Path) -> None:
    bad = tmp_path / "list.yaml"
    bad.write_text("- item1\n- item2\n", encoding="utf-8")
    reg = CapabilityRegistry(str(bad))
    with pytest.raises(ValueError, match="mapping"):
        reg.load()


# ---------------------------------------------------------------------------
# Non-list agents key raises ValueError (line 51)
# ---------------------------------------------------------------------------


def test_load_agents_not_a_list(tmp_path: Path) -> None:
    bad = tmp_path / "agents_map.yaml"
    bad.write_text(
        "version: '1.0'\nbrainstorm_project_template: 'df-{ticket_id}'\nagents: {key: value}\n",
        encoding="utf-8",
    )
    reg = CapabilityRegistry(str(bad))
    with pytest.raises(ValueError, match="list"):
        reg.load()


# ---------------------------------------------------------------------------
# Missing role_id raises ValueError (line 59)
# ---------------------------------------------------------------------------


def test_load_missing_role_id(tmp_path: Path) -> None:
    bad = tmp_path / "no_role_id.yaml"
    bad.write_text(
        "version: '1.0'\nbrainstorm_project_template: 'df-{ticket_id}'\nagents:\n"
        "  - display_name: Agent Without ID\n    skill_file: a.md\n    brainstorm_role: contributor\n",
        encoding="utf-8",
    )
    reg = CapabilityRegistry(str(bad))
    with pytest.raises(ValueError, match="missing 'role_id'"):
        reg.load()


# ---------------------------------------------------------------------------
# Invalid brainstorm_role raises ValueError (line 66)
# ---------------------------------------------------------------------------


def test_load_invalid_brainstorm_role(tmp_path: Path) -> None:
    bad = tmp_path / "bad_role.yaml"
    bad.write_text(
        "version: '1.0'\nbrainstorm_project_template: 'df-{ticket_id}'\nagents:\n"
        "  - role_id: backend\n    display_name: Backend\n    skill_file: b.md\n"
        "    brainstorm_role: owner\n",
        encoding="utf-8",
    )
    reg = CapabilityRegistry(str(bad))
    with pytest.raises(ValueError, match="Invalid brainstorm_role"):
        reg.load()


# ---------------------------------------------------------------------------
# Module-level get_registry / load_registry (lines 123-133)
# ---------------------------------------------------------------------------


def test_get_registry_before_load_raises() -> None:
    import src.services.capability_registry as mod

    original = mod._registry
    mod._registry = None
    try:
        with pytest.raises(RuntimeError, match="not loaded"):
            get_registry()
    finally:
        mod._registry = original


def test_load_registry_sets_and_returns(registry_file: Path) -> None:
    import src.services.capability_registry as mod

    original = mod._registry
    try:
        reg = load_registry(str(registry_file))
        assert isinstance(reg, CapabilityRegistry)
        assert get_registry() is reg
    finally:
        mod._registry = original


# ---------------------------------------------------------------------------
# SEC-T03: malformed brainstorm_project_template raises ValueError
# ---------------------------------------------------------------------------


def test_load_invalid_brainstorm_project_template(tmp_path: Path) -> None:
    bad = tmp_path / "bad_template.yaml"
    bad.write_text(
        "version: '1.0'\n"
        "brainstorm_project_template: 'evil-{ticket_id!r:.__class__.__mro__}'\n"
        "agents: []\n",
        encoding="utf-8",
    )
    reg = CapabilityRegistry(str(bad))
    with pytest.raises(ValueError, match="brainstorm_project_template"):
        reg.load()


def test_load_template_injection_attempt(tmp_path: Path) -> None:
    bad = tmp_path / "injection_template.yaml"
    bad.write_text(
        "version: '1.0'\n"
        "brainstorm_project_template: '{__import__(\"os\").system(\"id\")}'\n"
        "agents: []\n",
        encoding="utf-8",
    )
    reg = CapabilityRegistry(str(bad))
    with pytest.raises(ValueError, match="brainstorm_project_template"):
        reg.load()


def test_load_valid_template_with_prefix_suffix(tmp_path: Path) -> None:
    f = tmp_path / "registry.yaml"
    f.write_text(
        "version: '1.0'\n"
        "brainstorm_project_template: 'proj-{ticket_id}-v2'\n"
        "agents: []\n",
        encoding="utf-8",
    )
    reg = CapabilityRegistry(str(f))
    reg.load()
    assert reg.brainstorm_project_name("TKT-1") == "proj-TKT-1-v2"
