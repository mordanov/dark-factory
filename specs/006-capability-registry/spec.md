# Feature Specification: 006 — Agent Capability Registry & Dynamic Agent Selection

**Feature ID:** 006  
**Feature Name:** capability-registry  
**Status:** In Specification  
**Date:** 2026-06-26  
**Author:** product-manager

---

## 1. Problem Statement

The Orchestrator FSM engine currently uses a hardcoded `AGENT_FOR_STATE` dict to map FSM states to agent roles. This creates a single point of brittleness: adding, renaming, or rebalancing agents requires code changes in the FSM engine itself. There is also no machine-readable source of truth for what each agent is capable of, making LLM-assisted routing impossible.

The result is that ticket routing is rigid, undocumented, and not extensible without engineering effort.

---

## 2. Goals

1. Replace the hardcoded `AGENT_FOR_STATE` dict with a YAML-driven **Capability Registry** that is the single source of truth for all agent role metadata.
2. Enable **LLM-assisted dynamic agent selection**: the LLM can pick the most appropriate agent from registry-defined candidates, informed by ticket context and project memory.
3. Deliver a **CapabilityRegistry class** in `agent-dispatcher` that loads, queries, and exposes the registry to the rest of the system.
4. Deliver an **AgentSelector** in `orchestrator` that makes a fast, focused LLM call to select from candidates, with a deterministic fallback.
5. Write per-agent `credentials.json` before each agent spawn so agents always have fresh TM credentials.

---

## 3. Target Users / Actors

| Actor | Need |
|---|---|
| Orchestrator FSM | Needs candidate agent list per FSM transition, without hardcoding roles |
| Orchestrator LLM | Needs registry context in the prompt to assign `assigned_agent` to a valid role |
| Agent Dispatcher | Needs to load the registry at startup and include it in every job payload |
| Developer/Operator | Needs a single file (`registry.yaml`) to add/remove/reconfigure agents without touching Python code |

---

## 4. Scope

### 4.1 In Scope

| ID | Item |
|---|---|
| IN-01 | `development/agents/registry.yaml` — full registry with all 10 canonical agents |
| IN-02 | `agent-dispatcher/src/services/capability_registry.py` — CapabilityRegistry class |
| IN-03 | `agent-dispatcher/src/core/config.py` — `agent_registry_path` setting |
| IN-04 | `agent-dispatcher/src/main.py` — registry loaded once in FastAPI lifespan |
| IN-05 | `agent-dispatcher/src/services/reporter.py` — registry YAML included in every job payload |
| IN-06 | `agent-dispatcher/src/services/dispatcher_service.py` — `_write_credentials()` before spawn |
| IN-07 | `orchestrator/src/services/fsm/engine.py` — remove `AGENT_FOR_STATE`, add `candidate_agents` to `FSMEvaluation` |
| IN-08 | `orchestrator/src/services/fsm/agent_selector.py` — new module with focused LLM selection |
| IN-09 | `orchestrator/src/services/llm/orchestrator_llm.py` — inject `[AGENT REGISTRY]` section in prompt |
| IN-10 | `orchestrator/src/services/orchestrator_service.py` — validate `assigned_agent` against registry; call selector as fallback |
| IN-11 | `.gitignore` — add `development/**/credentials.json` |
| IN-12 | Unit tests for CapabilityRegistry, AgentSelector, and FSM engine changes |

### 4.2 Out of Scope

| Item | Reason |
|---|---|
| GUI for registry management | Future enhancement |
| Per-project capability overrides | Project-memory overrides already handle this |
| Agent load balancing | Future |
| Capability versioning | Future |
| New microservices | Not needed |
| Changes to ticket-manager | Not affected |
| Changes to user-input-manager frontend | Not affected |

---

## 5. Functional Requirements

### FR-001: Registry File
`development/agents/registry.yaml` must contain all 10 canonical agent entries with fields: `role_id`, `display_name`, `skill_file`, `coordinator`, `capabilities`, `fsm_ownership`, `preferred_for`, `brainstorm_also_for`, `brainstorm_role`. Top-level: `version: "1.0"`, `brainstorm_project_template: "df-{ticket_id}"`.

### FR-002: CapabilityRegistry Class
`CapabilityRegistry.load()` must parse the YAML and index agents by `role_id` and `fsm_ownership` state. Must expose: `get_candidates_for_state()`, `get_brainstorm_participants()`, `get_by_role_id()`, `all_role_ids()`, `to_yaml_string()`, `brainstorm_project_name()`.

### FR-003: Registry Loaded Once
Registry must be instantiated in FastAPI lifespan (startup), not per-request. Changes require service restart.

### FR-004: Registry in Job Payload
`reporter.py` must include `registry_yaml` (the full YAML string) in every orchestrator job trigger payload.

### FR-005: FSM Engine Refactored
`AGENT_FOR_STATE` dict deleted. `FSMEvaluation.candidate_agents: list[str]` replaces `assigned_agent: str | None`. `evaluate()` returns the list of role_ids that own the target FSM state.

### FR-006: Agent Selector
`orchestrator/src/services/fsm/agent_selector.py` must provide `select_agent(ticket, to_state, candidate_role_ids, registry_yaml, project_memory) -> str`. Single candidate returns immediately without LLM call. Empty candidates returns `"product-manager"`. Multiple candidates makes an LLM call with a 10-second timeout and falls back to `candidate_role_ids[0]` on any failure.

### FR-007: Registry in Orchestrator Prompt
`orchestrator_llm.py` must add a `[AGENT REGISTRY]` section to the user message when `registry_yaml` is present in `job_payload`. The system prompt must instruct the LLM that `assigned_agent` must be a `role_id` from the registry.

### FR-008: Assigned Agent Validation
After the orchestrator LLM returns a decision, `orchestrator_service.py` must validate `assigned_agent` against known role IDs from the registry. Unknown role IDs trigger a call to `select_agent()` as fallback (not a hard BLOCK).

### FR-009: Credentials Writer
`dispatcher_service.py` must call `_write_credentials(role_id)` before every `runner.run()`. The method writes `development/{role_id}/credentials.json` with `host`, `token`, `role`. Token is obtained from `TicketManagerClient.get_service_token()`.

### FR-010: Gitignore
`development/**/credentials.json` must be added to `.gitignore` at monorepo root.

---

## 6. Non-Functional Requirements

| ID | Requirement |
|---|---|
| NFR-01 | `select_agent()` never raises — always returns a valid role_id string |
| NFR-02 | Agent selector LLM call timeout ≤ 10 seconds |
| NFR-03 | Registry loaded once at startup — zero per-request file I/O |
| NFR-04 | Unit test coverage ≥ 80% on new modules (`capability_registry.py`, `agent_selector.py`) |
| NFR-05 | Role IDs use hyphenated format matching `run-agents.sh` exactly |
| NFR-06 | `credentials.json` is never committed to git |

---

## 7. Acceptance Criteria

| ID | Criterion | Verifiable By |
|---|---|---|
| AC-01 | `development/agents/registry.yaml` exists with all 10 agents | File check |
| AC-02 | `CapabilityRegistry.get_candidates_for_state("implementation")` returns `["backend", "frontend"]` | Unit test |
| AC-03 | `CapabilityRegistry.get_candidates_for_state("unknown")` returns `[]` | Unit test |
| AC-04 | `AGENT_FOR_STATE` no longer exists in `engine.py` | Code grep |
| AC-05 | `FSMEvaluation` has `candidate_agents: list[str]`, not `assigned_agent` | Code check |
| AC-06 | Orchestrator prompt includes `[AGENT REGISTRY]` section when `registry_yaml` in payload | Integration test / unit test |
| AC-07 | For a Python-backend ticket: LLM selects `backend` over `frontend` | Unit test with mock LLM |
| AC-08 | For a React UI ticket: LLM selects `frontend` over `backend` | Unit test with mock LLM |
| AC-09 | Invalid agent role in LLM output → selector fallback to first candidate (not hard crash) | Unit test |
| AC-10 | `credentials.json` written to `development/{role}/` before each agent spawn | Integration / unit test |
| AC-11 | `development/**/credentials.json` in `.gitignore` | File check |
| AC-12 | `select_agent()` with empty candidates returns `"product-manager"` | Unit test |
| AC-13 | `select_agent()` with single candidate returns it without LLM call | Unit test |
| AC-14 | All unit tests pass; ≥ 80% coverage on `capability_registry.py` and `agent_selector.py` | CI / pytest-cov |
| AC-15 | Services start successfully with registry loaded (checked in logs) | Docker Compose smoke test |

---

## 8. Assumptions & Open Questions

| # | Item |
|---|---|
| A-01 | `run-agents.sh` ROLES array already uses hyphenated IDs; no change needed there |
| A-02 | `TicketManagerClient` already has an internal `_token` attribute that can be exposed |
| A-03 | `OPENAI_MODEL` env var and `openai_api_key` already configured in orchestrator |
| A-04 | `agent-dispatcher` can write to `development/{role}/` — paths are reachable at runtime |
| OQ-01 | Should `select_agent()` be called from orchestrator or from dispatcher? — Architecture to decide |
| OQ-02 | Should `registry_yaml` be stored in the DB per job or always re-fetched from dispatcher? — Architecture to decide |

---

## 9. Dependencies

| Dependency | Owner | Status |
|---|---|---|
| `development/agents/` skill files (existing) | product-manager | Done — 10 agents already have skill files |
| `run-agents.sh` ROLES array | devops | Done — already uses correct IDs |
| Orchestrator OpenAI client | backend/architect | Already implemented |
| TM service account credentials | backend | Need to verify `get_service_token()` exists |

---

## 10. Milestone Order & Priorities

**Priority: Must Have (P0)**
- registry.yaml (IN-01) — everything depends on this
- CapabilityRegistry class (IN-02, IN-03, IN-04) — enables all downstream work
- FSM engine refactor (IN-07) — unblocks agent selector and orchestrator changes

**Priority: Should Have (P1)**
- Agent selector (IN-08) — core capability
- Reporter update (IN-05) — enables registry delivery
- Orchestrator LLM changes (IN-09, IN-10) — closes the loop

**Priority: Must Have for Safety (P0)**
- Credentials writer (IN-06) — agents can't auth without this
- Gitignore update (IN-11) — security requirement

**Priority: Required for Completeness (P1)**
- Unit tests (IN-12) — coverage gate at 80%

---

## 11. Definition of Done

1. All 10 functional requirements (FR-001 to FR-010) implemented.
2. All 15 acceptance criteria (AC-01 to AC-15) pass.
3. Code reviewed and approved by code-reviewer.
4. Unit tests pass with ≥ 80% coverage on new modules.
5. Security review completed by security-architect (credentials handling, token exposure).
6. No `AGENT_FOR_STATE` references remain in codebase.
7. No `credentials.json` files committed to git.
8. Deployment verified by devops (services start, registry loads, logs confirm).
