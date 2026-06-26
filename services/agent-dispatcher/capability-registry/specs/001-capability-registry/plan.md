# Implementation Plan: Agent Capability Registry & Dynamic Selection

**Branch**: `006-capability-registry` | **Date**: 2026-06-26 | **Spec**: [spec.md](spec.md)  
**Input**: Feature specification from `specs/001-capability-registry/spec.md`

## Summary

Replace the hardcoded `AGENT_FOR_STATE` dict in the Orchestrator FSM engine with a capability-driven registry (`development/agents/registry.yaml`) loaded at agent-dispatcher startup. The registry maps all 10 agent roles to FSM state ownership and capability tags. Dynamic LLM-assisted selection picks the best-fit agent when multiple candidates own the same FSM state. The registry YAML is forwarded in every Orchestrator job trigger payload so the LLM can produce grounded role assignments. A credentials file is written to each agent's working directory before spawn.

No new service is created. Two existing services are modified: `agent-dispatcher` and `orchestrator`.

## Technical Context

**Language/Version**: Python 3.12  
**Primary Dependencies**: FastAPI 0.115.5, Pydantic 2.10.3, SQLAlchemy 2.0.36, PyYAML (already available via transitive deps), OpenAI SDK (already used by orchestrator)  
**Storage**: No new storage. Registry lives on the filesystem (`development/agents/registry.yaml`).  
**Testing**: pytest (both services already use it), pytest-asyncio for async agent selector tests  
**Target Platform**: Linux container (Docker Compose), Python 3.12  
**Project Type**: Distributed HTTP microservices — two services modified  
**Performance Goals**: Agent selection ≤ 10s worst case, ≤ 2s median; registry load ≤ 500ms added startup cost  
**Constraints**: Registry loaded once at startup (no per-request file I/O); `select_agent()` never raises; credentials.json gitignored  
**Scale/Scope**: 10 agent roles; ~8 FSM states; single-instance services in current deployment

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| Gate | Status | Notes |
|------|--------|-------|
| No new service created | ✅ PASS | Changes touch `agent-dispatcher` and `orchestrator` only |
| Single source of truth for agent roles | ✅ PASS | `registry.yaml` is the only place role IDs are defined |
| Fallback always defined | ✅ PASS | `select_agent()` returns `candidate_role_ids[0]` on any failure |
| Registry loaded once at startup | ✅ PASS | FastAPI lifespan hook; no per-request I/O |
| Credentials gitignored | ✅ PASS | `.gitignore` entry added as part of this feature |
| Role IDs hyphenated and matching `run-agents.sh` | ✅ PASS | `VALID_AGENT_IDS` in `constants.py` must be updated from underscore to hyphenated format |
| `AGENT_FOR_STATE` deleted | ✅ PASS (planned) | Deleted from `engine.py`; no other file may reintroduce it |

**One pre-existing violation to migrate**: `VALID_AGENT_IDS` in `agent-dispatcher/src/core/constants.py` currently uses underscore format (`software_architect`, `project_manager`, etc.). This must be updated to hyphenated format as part of this feature. All callers that look up against this frozenset must be updated simultaneously.

## Project Structure

### Documentation (this feature)

```text
specs/001-capability-registry/
├── plan.md              ← this file
├── research.md          ← Phase 0 output
├── data-model.md        ← Phase 1 output
├── contracts/           ← Phase 1 output (registry YAML schema contract)
└── tasks.md             ← Phase 2 output (/speckit-tasks — NOT created here)
```

### Source Code Layout (files created or modified)

```text
development/agents/
└── registry.yaml                          ← NEW: full capability registry (10 agents)

services/agent-dispatcher/
├── src/
│   ├── core/
│   │   ├── config.py                      ← MODIFIED: add agent_registry_path + resolved_registry_path
│   │   └── constants.py                   ← MODIFIED: VALID_AGENT_IDS → hyphenated format
│   ├── services/
│   │   ├── capability_registry.py         ← NEW: CapabilityRegistry + AgentCapability
│   │   ├── dispatcher_service.py          ← MODIFIED: _write_credentials() + call before spawn
│   │   └── reporter.py                    ← MODIFIED: include registry_yaml in job payload
│   └── main.py                            ← MODIFIED: load registry in lifespan
└── tests/unit/
    ├── test_capability_registry.py        ← NEW
    └── test_dispatcher_credentials.py    ← NEW

services/orchestrator/
├── src/
│   ├── services/
│   │   ├── fsm/
│   │   │   ├── engine.py                  ← MODIFIED: remove AGENT_FOR_STATE, FSMEvaluation.candidate_agents
│   │   │   └── agent_selector.py          ← NEW: select_agent() LLM call
│   │   ├── llm/
│   │   │   └── orchestrator_llm.py        ← MODIFIED: [AGENT REGISTRY] section + _summarize_registry()
│   │   └── orchestrator_service.py        ← MODIFIED: pass job_payload to LLM, validate assigned_agent
└── tests/unit/
    ├── test_fsm_engine.py                 ← MODIFIED: remove AGENT_FOR_STATE tests, add candidate_agents tests
    └── test_agent_selector.py             ← NEW

.gitignore (monorepo root)                 ← MODIFIED: add development/**/credentials.json
```

## Complexity Tracking

No constitution violations requiring justification. The `VALID_AGENT_IDS` migration is a bug fix (wrong format), not additional complexity.

---

## Phase 0: Research

*All technical unknowns were resolved by reading the existing codebase. No external research required.*

See [research.md](research.md) for decisions and rationale.

---

## Phase 1: Design & Contracts

See [data-model.md](data-model.md) for entity definitions and field-level design.

See [contracts/registry-schema.md](contracts/registry-schema.md) for the `registry.yaml` schema contract.

---

## Implementation Sequence (for /speckit-tasks)

The tasks must be implemented in this dependency order to avoid broken intermediate states:

1. **registry.yaml** — the file all other changes depend on
2. **CapabilityRegistry class** in agent-dispatcher — loader needed before lifespan and reporter changes
3. **Config additions** in agent-dispatcher — `resolved_registry_path` needed by lifespan
4. **VALID_AGENT_IDS migration** — must be done atomically with lifespan wiring (service won't start if IDs mismatch)
5. **Lifespan wiring** in agent-dispatcher/main.py — loads registry at startup
6. **Reporter update** — can include registry in payload once it is available from lifespan
7. **FSM engine changes** — remove AGENT_FOR_STATE, return candidate_agents (self-contained)
8. **agent_selector.py** in orchestrator — depends on FSMEvaluation.candidate_agents shape
9. **orchestrator_llm.py** — inject [AGENT REGISTRY] section (depends on payload contract from reporter)
10. **orchestrator_service.py** — validate assigned_agent, call agent_selector fallback (depends on 7, 8, 9)
11. **Credentials writer** in dispatcher_service.py — independent of registry but needs TicketManagerClient.get_service_token()
12. **.gitignore update** — can be done at any point
13. **Unit tests** — each module tested immediately after it is written
