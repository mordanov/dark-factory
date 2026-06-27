# Research: Agent Capability Registry & Dynamic Selection

**Date**: 2026-06-26  
**Status**: Complete — no external unknowns; all decisions resolved from codebase

---

## Decision 1: Registry file format and location

**Decision**: YAML file at `development/agents/registry.yaml` (alongside existing skill `.md` files)  
**Rationale**: The `development/agents/` directory already holds all 10 agent skill files. Co-locating the registry makes the relationship explicit and ensures a single directory is the source of truth for everything agent-related. YAML is human-editable, supports comments, and is already used elsewhere in the monorepo.  
**Alternatives considered**:
- JSON: rejected — no comments, harder to read/edit by agent authors
- Database table: rejected — adds a migration and a service dependency for what is purely static config
- Inline Python dict (extend existing constants.py): rejected — couples two services to the same file and violates registry-as-single-source-of-truth

---

## Decision 2: Where CapabilityRegistry lives (which service)

**Decision**: `agent-dispatcher/src/services/capability_registry.py`  
**Rationale**: The agent-dispatcher is the process that (a) reads agent skill files from disk, (b) knows which agent to spawn, and (c) sends the job-trigger payload to the orchestrator. It already has `AGENT_PROMPTS_DIR` pointing to the agents directory. The registry is a natural extension of that ownership.  
**Alternatives considered**:
- In orchestrator: rejected — the orchestrator does not have access to the agents filesystem directory and should not have it
- Shared library: rejected — there is no shared Python package infrastructure in this monorepo; each service is self-contained

---

## Decision 3: How registry reaches the Orchestrator

**Decision**: Serialised YAML string in every job-trigger payload (`payload["registry_yaml"]`)  
**Rationale**: The orchestrator already receives an open-ended `payload: dict` in `JobCreate`. Forwarding the raw YAML string avoids a new API endpoint, keeps the orchestrator stateless with respect to registry state, and ensures the LLM always sees a consistent snapshot. The string is ~3–5 KB — negligible payload overhead.  
**Alternatives considered**:
- Orchestrator reads registry.yaml directly: rejected — cross-service filesystem coupling; orchestrator container doesn't mount the agents directory
- New HTTP endpoint on agent-dispatcher to fetch registry: rejected — unnecessary service call on every orchestration cycle; adds latency and a failure mode
- Inline the registry content in orchestrator's own config: rejected — duplicates the single source of truth

---

## Decision 4: FSMEvaluation field change (`assigned_agent` → `candidate_agents`)

**Decision**: Replace `assigned_agent: str | None` with `candidate_agents: list[str]` in `FSMEvaluation` dataclass  
**Rationale**: The FSM engine's responsibility is to determine WHAT to do (which state, which gates). Determining WHO does it belongs to the selection layer. The change also unblocks multi-agent states (implementation: backend + frontend) which the current design cannot express.  
**Impact**: All callers of `fsm.evaluate()` must be updated:
- `orchestrator_service.py` — currently reads `fsm_eval.assigned_agent` in `_apply_wait()` and in `_run()`; must switch to `candidate_agents`
- `orchestrator_llm.py` — passes `fsm_eval` to `_build_user_message()`; the `agent_id` field in the poll event JSON will become `null` (selection hasn't happened yet at that point)
- Tests in `test_fsm_engine.py` — must be updated to assert `candidate_agents` not `assigned_agent`

---

## Decision 5: VALID_AGENT_IDS migration (underscore → hyphen)

**Decision**: Replace all 10 entries in `VALID_AGENT_IDS` frozenset with hyphenated equivalents  
**Rationale**: The current constants use `software_architect`, `project_manager`, `code_reviewer`, `security_architect` — underscore format. `run-agents.sh` and the registry use `software-architect`, `product-manager`, `code-reviewer`, `security-architect` — hyphenated format. This mismatch would cause all newly-assigned agents to fail the whitelist check. The migration must be atomic: update `constants.py`, `brainstorm_agents` default in `config.py`, and any tests that reference the old names.  
**Mapping**:

| Old (underscore) | New (hyphenated) |
|---|---|
| `project_manager` | `product-manager` |
| `software_architect` | `software-architect` |
| `security_architect` | `security-architect` |
| `code_reviewer` | `code-reviewer` |
| `backend` | `backend` (unchanged) |
| `frontend` | `frontend` (unchanged) |
| `designer` | `designer` (unchanged) |
| `autotester` | `autotester` (unchanged) |
| `devops` | `devops` (unchanged) |
| `project_administrator` | `project-administrator` |

**Note**: The `config.py` default for `brainstorm_agents` is `"software_architect,security_architect"` — this must become `"software-architect,security-architect"`.

---

## Decision 6: Agent selector — separate LLM call vs. reuse orchestrator call

**Decision**: Separate lightweight LLM call in `orchestrator/src/services/fsm/agent_selector.py`  
**Rationale**: The selector is a focused, stateless operation that needs max 30 tokens output. Embedding it inside the full orchestrator LLM call would require restructuring the 2000-token output schema and complicate the already complex prompt. A separate call with a tiny prompt and strict JSON mode is faster, cheaper, and easier to test in isolation.  
**Parameters**: `max_tokens=30`, `temperature=0.0`, `response_format={"type": "json_object"}`, `timeout=10.0s`

---

## Decision 7: Fallback ordering when selection fails

**Decision**: Always return `candidate_role_ids[0]` as fallback  
**Rationale**: The registry defines FSM state ownership in a deterministic order (YAML list order). The first candidate in the list is the primary owner. This makes the fallback predictable and testable.  
**Fallback triggers**: LLM timeout, LLM API error, LLM returns role not in candidates list, empty candidates list (special case: return `"product-manager"` as the system-wide safe default)

---

## Decision 8: Credentials file structure

**Decision**: Write `development/{role_id}/credentials.json` with `host`, `token`, `role` fields  
**Rationale**: Agent skill files (e.g., `backend-developer-python.md`) instruct agents to read `credentials.json` from their working directory. The structure matches what agents expect. The dispatcher already has a `TicketManagerClient` that holds a valid token internally (`_token` field). A new `get_service_token()` method exposes it without re-authentication.  
**Security**: File is written immediately before spawn and covered by the gitignore pattern `development/**/credentials.json`.

---

## Decision 9: `_build_user_message()` signature change

**Decision**: Add `job_payload: dict` parameter to `call_orchestrator_llm()` and thread it through `_build_user_message()`  
**Rationale**: The `job_payload` is already present on the `Job` ORM model and read in `orchestrator_service._run()`. Passing it into the LLM call is a minimal, backward-compatible change — existing callers that pass `{}` will simply get no registry section in the prompt (graceful degradation).

---

## Resolved: No NEEDS CLARIFICATION items

All design questions were resolved by reading:
- `engine.py` — exact current shape of `FSMEvaluation` and `AGENT_FOR_STATE`
- `constants.py` — the underscore/hyphen mismatch issue
- `config.py` — `brainstorm_agents` default string format
- `dispatcher_service.py` — how spawning currently works, where `_write_credentials()` fits
- `reporter.py` — exact call site for `_trigger_orchestrator()` and current payload shape
- `main.py` — lifespan pattern for registry injection
- `orchestrator_llm.py` — `_build_user_message()` structure, `job_payload` threading
- `orchestrator_service.py` — how `fsm_eval.assigned_agent` is currently used in `_apply_wait()`
