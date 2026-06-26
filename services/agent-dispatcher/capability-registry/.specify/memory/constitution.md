# Dark Factory — Agent Capability Registry Constitution

## Identity

This constitution governs two tightly coupled changes:

1. **Agent Capability Registry** — a structured YAML file at
   `development/agents/registry.yaml` that maps every agent role
   to its domain/skill capabilities and FSM ownership.

2. **Dynamic Agent Selection** — replaces the hardcoded
   `AGENT_FOR_STATE` dict in the Orchestrator FSM engine with an
   LLM-assisted selection that consults the registry and the ticket
   context to pick the best agent(s) for each transition.

No new service is created. Changes touch:
- `development/agents/registry.yaml` (new file)
- `agent-dispatcher/src/services/capability_registry.py` (new)
- `orchestrator/src/services/fsm/agent_selector.py` (new)
- `orchestrator/src/services/fsm/engine.py` (modified)
- `orchestrator/src/services/llm/orchestrator_llm.py` (modified)
- `orchestrator/src/services/orchestrator_service.py` (modified)

---

## Core Principles

### 1. Registry is the single source of truth for agent metadata

`development/agents/registry.yaml` is the only place that defines:
- Canonical role IDs (hyphenated: `backend`, `software-architect`)
- Display names
- Skill file names
- Domain/skill capability tags
- FSM state ownership
- Coordinator flag
- Brainstorm participation rules

No service hardcodes role IDs or capability assumptions.
The orchestrator reads the registry via the agent-dispatcher's
`CapabilityRegistry` class at startup.

### 2. Role IDs are hyphenated and match run-agents.sh exactly

The canonical role IDs are: `project-administrator`, `product-manager`,
`software-architect`, `security-architect`, `backend`, `frontend`,
`designer`, `code-reviewer`, `autotester`, `devops`.

These match `run-agents.sh` `ROLES` array exactly.
The previous `AGENT_FOR_STATE` dict used underscore names
(`project_manager`, `software_architect`) — those are replaced.

### 3. LLM selects agents, registry provides context

The Orchestrator LLM call receives the capability registry as a new
`[AGENT REGISTRY]` section in the user message. The LLM selects
`assigned_agent` from the registry based on:
- Current FSM state and `to_state`
- Ticket type (`feature`, `bugfix`, `improvement`)
- Ticket title and description
- Project context (from project memory)
- Agent capability tags

The registry section shows: `role_id → capabilities + fsm_ownership`.
The LLM must select a `role_id` that exists in the registry.
The `assigned_agent` field in the decision JSON is validated against
the registry — unknown role IDs are rejected and treated as `BLOCK`.

### 4. Hardcoded AGENT_FOR_STATE is removed

`orchestrator/src/services/fsm/engine.py` currently contains:
```python
AGENT_FOR_STATE: dict[str, str] = {
    "triage": "project_manager",
    ...
}
```
This dict is deleted entirely. The FSM engine no longer assigns agents.
`FSMEvaluation` changes: `assigned_agent: str | None` becomes
`candidate_agents: list[str]` — agents that own the target FSM state.
The LLM picks the final `assigned_agent` from these candidates.

### 5. Credentials are written by the Dispatcher before agent spawn

Before spawning any agent, `agent-dispatcher` writes
`development/{role}/credentials.json` with a fresh TM API token:
```json
{
  "host": "https://ticket-manager.dark-factory.miveralta.ru",
  "username": "{role}@agents.local",
  "password": "<generated-per-run>"
}
```
The dispatcher uses its own TM service account to get a token,
then writes per-agent credentials. Agents read `credentials.json`
from their working directory as per their skill file instructions.

The credentials file is gitignored (`**/credentials.json`).

### 6. Capability registry is loaded once at startup

`CapabilityRegistry` is instantiated once when the agent-dispatcher
starts (in FastAPI lifespan). It reads `registry.yaml` from
`AGENT_PROMPTS_DIR/../registry.yaml` (relative to skill file dir).
Changes to `registry.yaml` require a service restart.

A copy of the registry (serialized as YAML string) is sent to the
Orchestrator in every job trigger payload so the Orchestrator LLM
always has the current registry without querying the dispatcher.

---

## Registry Schema (`development/agents/registry.yaml`)

```yaml
version: "1.0"

# Brainstorm project name convention for multi-agent sessions
brainstorm_project_template: "df-{ticket_id}"

agents:
  - role_id: project-administrator
    display_name: Project Administrator
    skill_file: project-administrator.md
    coordinator: false
    capabilities:
      - metrics_collection
      - reporting
      - ticket_management
      - agent_bootstrapping
      - sqlite_database
    fsm_ownership: []        # cross-cutting, not FSM-state-bound
    brainstorm_role: contributor

  - role_id: product-manager
    display_name: Product Manager
    skill_file: product-manager.md
    coordinator: true        # drives workflow in brainstorm sessions
    capabilities:
      - requirements
      - scope_definition
      - backlog_management
      - acceptance_criteria
      - stakeholder_alignment
      - prioritization
    fsm_ownership:
      - triage
      - specification
    brainstorm_role: coordinator

  - role_id: software-architect
    display_name: Software Architect
    skill_file: software-architect.md
    coordinator: false
    capabilities:
      - system_design
      - architecture_decisions
      - api_contracts
      - data_modeling
      - adr_generation
      - integration_design
      - evolutionary_architecture
    fsm_ownership:
      - architecture_review
    brainstorm_role: contributor

  - role_id: security-architect
    display_name: Security Architect
    skill_file: security-architect.md
    coordinator: false
    capabilities:
      - threat_modeling
      - security_review
      - auth_design
      - vulnerability_assessment
      - privacy_design
      - secrets_management
    fsm_ownership:
      - security_review
    brainstorm_also_for:
      - architecture_review   # participates in arch brainstorm
    brainstorm_role: contributor

  - role_id: backend
    display_name: Backend Developer Python
    skill_file: backend-developer-python.md
    coordinator: false
    capabilities:
      - python_backend
      - fastapi
      - sqlalchemy
      - database_migrations
      - api_implementation
      - background_jobs
      - server_side_validation
      - backend_testing
    fsm_ownership:
      - implementation
    preferred_for:
      - python
      - api
      - database
      - migration
      - backend
    brainstorm_role: contributor

  - role_id: frontend
    display_name: Frontend Developer React
    skill_file: frontend-developer-react.md
    coordinator: false
    capabilities:
      - react
      - typescript
      - vite
      - zustand
      - ui_implementation
      - state_management
      - frontend_testing
      - accessibility
    fsm_ownership:
      - implementation
    preferred_for:
      - react
      - frontend
      - ui
      - component
      - typescript
    brainstorm_role: contributor

  - role_id: designer
    display_name: UI/UX Designer
    skill_file: designer.md
    coordinator: false
    capabilities:
      - ux_design
      - interaction_design
      - information_architecture
      - accessibility_design
      - design_system
      - wireframing
    fsm_ownership:
      - specification         # parallel with product-manager
    brainstorm_role: contributor

  - role_id: code-reviewer
    display_name: Code Reviewer
    skill_file: code-reviewer.md
    coordinator: false
    capabilities:
      - code_review
      - quality_gates
      - security_code_review
      - test_coverage_verification
      - maintainability_review
      - architecture_compliance
    fsm_ownership:
      - code_review
    brainstorm_role: contributor

  - role_id: autotester
    display_name: Autotester / QA
    skill_file: autotester.md
    coordinator: false
    capabilities:
      - test_automation
      - test_strategy
      - regression_testing
      - integration_testing
      - api_testing
      - quality_reporting
      - bug_reproduction
    fsm_ownership:
      - testing
    brainstorm_role: contributor

  - role_id: devops
    display_name: DevOps / Platform
    skill_file: devops.md
    coordinator: false
    capabilities:
      - deployment
      - docker
      - cicd
      - infrastructure_as_code
      - monitoring
      - release_management
      - rollback
      - nginx
    fsm_ownership:
      - release
    brainstorm_role: contributor
```

---

## Agent Selector — Selection Logic

`orchestrator/src/services/fsm/agent_selector.py`

The selector is called from `orchestrator_service.py` after the FSM
evaluates a ticket. It provides the LLM with candidate agents and
lets it pick the best one.

```
Input:
  ticket: TmTicket
  to_state: str                    (FSM transition target)
  candidate_role_ids: list[str]    (agents that own to_state)
  registry_yaml: str               (full registry as YAML string)
  project_memory: str | None

Output:
  selected_role_id: str
```

The selector makes a **separate, lightweight LLM call** (not the
full orchestrator call) with a focused prompt:

```
System: You are selecting the best agent for a Dark Factory task.
Return ONLY a JSON object: { "selected": "<role_id>" }
The selected role_id must be from the candidates list.

User:
[TICKET]
title: {ticket.title}
type: {ticket.ticket_type}
description (first 300 chars): {ticket.description[:300]}

[TARGET FSM STATE]
{to_state}

[CANDIDATE AGENTS]
{candidate_role_ids with their capabilities from registry}

[PROJECT MEMORY SUMMARY]
{project_memory[:500] if available}

Select the most appropriate agent for this ticket.
If multiple candidates equally match, prefer the first in the list.
```

Uses `OPENAI_MODEL` (same as orchestrator). Max tokens: 50.
On any error or invalid response: falls back to `candidate_role_ids[0]`.
Timeout: 10 seconds (must be fast — this is in the hot path).

---

## FSMEvaluation Changes

`orchestrator/src/services/fsm/engine.py`

```python
# Before
@dataclass
class FSMEvaluation:
    assigned_agent: str | None
    ...

# After
@dataclass
class FSMEvaluation:
    candidate_agents: list[str]  # role_ids that own to_state
    ...
    # assigned_agent is removed — set by agent_selector after LLM call
```

`evaluate()` no longer calls `AGENT_FOR_STATE[to_state]`.
Instead it returns `candidate_agents` from registry lookup:
```python
fsm_ownership_index: dict[str, list[str]]  # built from registry at startup
# e.g. {"implementation": ["backend", "frontend"], "code_review": ["code-reviewer"]}
```

---

## Registry Delivery to Orchestrator

Agent-dispatcher includes registry in every job trigger payload:

```python
# reporter.py
payload = {
    "registry_yaml": capability_registry.to_yaml_string(),
    # ... other fields
}
```

`orchestrator_llm.py` adds `[AGENT REGISTRY]` section to prompt
using `payload.get("registry_yaml")`.

---

## Validated Output

After the orchestrator LLM returns its decision, `orchestrator_service.py`
validates `decision.decision.assigned_agent` against the registry:

```python
valid_roles = [a["role_id"] for a in registry["agents"]]
if assigned_agent not in valid_roles:
    # treat as BLOCK with error message
    raise FSMError(f"Unknown agent role: {assigned_agent}")
```

---

## Files Changed / Created

| File | Change |
|---|---|
| `development/agents/registry.yaml` | **New** — full capability registry |
| `agent-dispatcher/src/services/capability_registry.py` | **New** — YAML loader + querier |
| `agent-dispatcher/src/core/config.py` | Add `registry_path` setting |
| `agent-dispatcher/src/services/dispatcher_service.py` | Write credentials.json before spawn |
| `agent-dispatcher/src/services/reporter.py` | Include registry in job payload |
| `agent-dispatcher/src/main.py` | Load registry in lifespan |
| `orchestrator/src/services/fsm/engine.py` | Remove `AGENT_FOR_STATE`, add `candidate_agents` |
| `orchestrator/src/services/fsm/agent_selector.py` | **New** — LLM selection |
| `orchestrator/src/services/llm/orchestrator_llm.py` | Inject `[AGENT REGISTRY]` section |
| `orchestrator/src/services/orchestrator_service.py` | Call agent_selector, validate result |

---

## Testing Requirements

### Unit tests — `test_capability_registry.py`
- `load()` succeeds with valid YAML
- `get_candidates_for_state("implementation")` returns `["backend", "frontend"]`
- `get_candidates_for_state("unknown")` returns `[]`
- `to_yaml_string()` is valid YAML
- `get_by_role_id("backend")` returns correct entry
- Unknown role returns None

### Unit tests — `test_agent_selector.py`
- Single candidate → returns it without LLM call
- Multiple candidates → LLM picks one
- LLM returns invalid role → fallback to first candidate
- LLM timeout → fallback to first candidate
- LLM called with correct system + user message structure

### Unit tests — `test_fsm_engine.py` (updates)
- `evaluate()` returns `candidate_agents` list, not `assigned_agent`
- `AGENT_FOR_STATE` no longer exists (import check)
- `architecture_review` → candidates include `software-architect` and `security-architect`
- `implementation` → candidates include both `backend` and `frontend`

### Unit tests — orchestrator validation
- Valid role_id in decision → passes
- Unknown role_id in decision → raises FSMError

---

## Definition of Done

1. `development/agents/registry.yaml` exists with all 10 agents
2. `CapabilityRegistry.get_candidates_for_state("implementation")` returns `["backend", "frontend"]`
3. Orchestrator prompt includes `[AGENT REGISTRY]` section when registry_yaml in payload
4. For a Python-backend ticket: LLM selects `backend` over `frontend`
5. For a React UI ticket: LLM selects `frontend` over `backend`
6. Invalid agent role in LLM output → BLOCK with clear error
7. `AGENT_FOR_STATE` dict no longer exists in engine.py
8. Credentials.json written to `development/{role}/` before each spawn
9. All unit tests pass; ≥ 80% coverage on new modules

---

## Principles That Must Never Be Violated

- **Registry is the only place** role IDs are defined — no hardcoded role strings elsewhere
- **LLM selects, registry constrains** — LLM cannot pick a role outside the registry
- **Fallback is always defined** — agent_selector never throws; it always returns a role_id
- **Credentials.json is gitignored** — never committed
- **Registry loaded once at startup** — no per-request file I/O
