# Data Model: Agent Capability Registry & Dynamic Selection

**Date**: 2026-06-26

---

## AgentCapability (dataclass — agent-dispatcher)

Represents one agent role entry parsed from `registry.yaml`.

| Field | Type | Description |
|-------|------|-------------|
| `role_id` | `str` | Hyphenated unique identifier. Must match `run-agents.sh` ROLES array exactly. |
| `display_name` | `str` | Human-readable label shown in logs and brainstorm sessions. |
| `skill_file` | `str` | Filename of the agent's skill prompt (e.g., `backend-developer-python.md`). |
| `coordinator` | `bool` | True if this agent drives multi-agent brainstorm sessions. |
| `capabilities` | `list[str]` | Domain/skill capability tags (e.g., `python_backend`, `react`, `threat_modeling`). |
| `fsm_ownership` | `list[str]` | FSM states this agent is the primary owner of. |
| `preferred_for` | `list[str]` | Keyword hints injected into the agent-selector LLM prompt to bias selection. |
| `brainstorm_also_for` | `list[str]` | FSM states where this agent participates in brainstorm without owning the state. |
| `brainstorm_role` | `str` | `"coordinator"` or `"contributor"`. Determines role in brainstorm protocol. |

---

## CapabilityRegistry (class — agent-dispatcher)

In-memory index loaded once at startup from `registry.yaml`.

| Attribute | Type | Description |
|-----------|------|-------------|
| `_path` | `Path` | Resolved filesystem path to `registry.yaml`. |
| `_agents` | `list[AgentCapability]` | Ordered list of all agents (preserves YAML order). |
| `_by_role` | `dict[str, AgentCapability]` | Role ID → agent for O(1) lookup. |
| `_by_state` | `dict[str, list[AgentCapability]]` | FSM state → owning agents. |
| `brainstorm_project_template` | `str` | Template string for brainstorm project names, e.g. `"df-{ticket_id}"`. |
| `_raw_yaml` | `str` | Raw YAML text, forwarded to Orchestrator in job payloads. |

**Methods**:

| Method | Returns | Description |
|--------|---------|-------------|
| `load()` | `None` | Reads and parses registry file. Raises `FileNotFoundError` or `ValueError`. |
| `get_candidates_for_state(fsm_state)` | `list[AgentCapability]` | Agents that own the given FSM state. Returns `[]` for unknown states. |
| `get_brainstorm_participants(fsm_state)` | `list[AgentCapability]` | State owners plus agents with `fsm_state` in `brainstorm_also_for`. |
| `get_by_role_id(role_id)` | `AgentCapability \| None` | Exact role lookup. Returns `None` if not found. |
| `all_role_ids()` | `list[str]` | All role IDs in registry order. |
| `to_yaml_string()` | `str` | Raw YAML for injection into LLM prompts. |
| `brainstorm_project_name(ticket_id)` | `str` | Formats brainstorm project name from template. |

---

## FSMEvaluation (dataclass — orchestrator, modified)

| Field | Old Type | New Type | Change |
|-------|----------|----------|--------|
| `action` | `str` | `str` | Unchanged |
| `from_state` | `str \| None` | `str \| None` | Unchanged |
| `to_state` | `str \| None` | `str \| None` | Unchanged |
| `assigned_agent` | `str \| None` | — | **REMOVED** |
| `candidate_agents` | — | `list[str]` | **NEW** — role IDs that own `to_state` |
| `blocked_reason` | `str \| None` | `str \| None` | Unchanged |
| `gates_to_evaluate` | `list[str]` | `list[str]` | Unchanged |
| `generate_adr` | `bool` | `bool` | Unchanged |
| `context_distiller_trigger` | `bool` | `bool` | Unchanged |
| `errors` | `list[str]` | `list[str]` | Unchanged |

**Migration note**: `fsm.evaluate()` callers in `orchestrator_service.py` currently read `fsm_eval.assigned_agent` in `_apply_wait()`. After migration: `_apply_wait()` passes `assigned_agent=None` (or omits it), since assignment happens after selection, not in the FSM.

---

## Settings additions (agent-dispatcher config.py)

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `agent_registry_path` | `str` | `""` | Override path to `registry.yaml`. Empty = use `resolved_registry_path`. |
| `resolved_registry_path` (property) | `str` | computed | `Path(agent_prompts_dir).parent / "registry.yaml"` when `agent_registry_path` is empty. |

---

## Orchestrator job payload additions

The `payload` dict in `JobCreate` gains a new key forwarded from agent-dispatcher:

| Key | Type | Description |
|-----|------|-------------|
| `registry_yaml` | `str` | Full raw YAML content of `registry.yaml`. Present on all job triggers from agent-dispatcher. Empty string for jobs triggered by other sources (backward-compatible). |

---

## Agent Credentials File (written to filesystem, not persisted to DB)

File path: `development/{role_id}/credentials.json`

| Field | Type | Description |
|-------|------|-------------|
| `host` | `str` | Ticket Manager base URL (from `settings.ticket_manager_base_url`). |
| `token` | `str` | Valid service account access token (from `TicketManagerClient.get_service_token()`). |
| `role` | `str` | The agent's role ID (hyphenated). |

**Lifecycle**: Written immediately before `runner.run()`. Not read back by the dispatcher. Gitignored via `development/**/credentials.json`.

---

## VALID_AGENT_IDS migration (agent-dispatcher constants.py)

The frozenset is replaced with hyphenated IDs matching the registry:

```
Before                  After
─────────────────────   ──────────────────────
"project_manager"    →  "product-manager"
"software_architect" →  "software-architect"
"security_architect" →  "security-architect"
"code_reviewer"      →  "code-reviewer"
"project_administrator" (unchanged format, but confirm)
                     →  "project-administrator"
"backend"            →  "backend"            (unchanged)
"frontend"           →  "frontend"           (unchanged)
"designer"           →  "designer"           (unchanged)
"autotester"         →  "autotester"         (unchanged)
"devops"             →  "devops"             (unchanged)
```
