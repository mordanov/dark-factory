# Tasks: Agent Capability Registry & Dynamic Selection

**Input**: Design documents from `specs/001-capability-registry/`  
**Prerequisites**: plan.md ✅ spec.md ✅ research.md ✅ data-model.md ✅ contracts/ ✅

**Organization**: Tasks grouped by user story to enable independent implementation and testing.  
**Tests**: Unit tests included per constitution requirements (≥80% coverage on new modules).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: User story this task belongs to (US1–US4)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Foundational changes that unlock all user stories. Must complete before any story work.

- [ ] T001 Create `development/agents/registry.yaml` with all 10 agents per constitution schema (`development/agents/registry.yaml`)
- [ ] T002 Update `VALID_AGENT_IDS` frozenset in `services/agent-dispatcher/src/core/constants.py` to hyphenated format (10 entries: `product-manager`, `software-architect`, `security-architect`, `code-reviewer`, `project-administrator`, `backend`, `frontend`, `designer`, `autotester`, `devops`)
- [ ] T003 Update `brainstorm_agents` default in `services/agent-dispatcher/src/core/config.py` from `"software_architect,security_architect"` to `"software-architect,security-architect"`
- [ ] T004 Add `development/**/credentials.json` to monorepo root `.gitignore`

**Checkpoint**: Registry file exists with all 10 agents; hyphenated IDs are consistent across constants, config, and YAML.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: `CapabilityRegistry` class and service wiring — everything else depends on this.

**⚠️ CRITICAL**: US1, US2, US3 cannot begin until this phase is complete.

- [ ] T005 Implement `AgentCapability` dataclass and `CapabilityRegistry` class in `services/agent-dispatcher/src/services/capability_registry.py` (all public methods: `load`, `get_candidates_for_state`, `get_brainstorm_participants`, `get_by_role_id`, `all_role_ids`, `to_yaml_string`, `brainstorm_project_name`)
- [ ] T006 Add `agent_registry_path` field and `resolved_registry_path` property to `Settings` in `services/agent-dispatcher/src/core/config.py`
- [ ] T007 Wire `CapabilityRegistry` into FastAPI lifespan in `services/agent-dispatcher/src/main.py`: instantiate, call `.load()`, log count; expose `get_registry()` function for dependency injection
- [ ] T008 [P] Write unit tests for `CapabilityRegistry` in `services/agent-dispatcher/tests/unit/test_capability_registry.py` (all 8 test cases from spec: load succeeds, candidates for implementation, unknown state returns [], brainstorm participants includes also_for, get_by_role_id found/not found, brainstorm_project_name, to_yaml_string valid)

**Checkpoint**: `CapabilityRegistry.load()` runs at service startup; `get_registry()` returns the loaded instance; all 8 unit tests pass.

---

## Phase 3: User Story 1 — Registry-Driven Agent Assignment (Priority: P1) 🎯 MVP

**Goal**: FSM engine returns candidate role IDs; orchestrator LLM receives the registry; invalid assignments are blocked.

**Independent Test**: Send a ticket titled "Implement PostgreSQL migration" through the full pipeline and verify `backend` is assigned; send "Add React component" and verify `frontend` is assigned. Verify `AGENT_FOR_STATE` no longer exists in `engine.py`.

### Implementation for User Story 1

- [ ] T009 [US1] Modify `FSMEvaluation` dataclass in `services/orchestrator/src/services/fsm/engine.py`: remove `assigned_agent: str | None`, add `candidate_agents: list[str]`; remove `AGENT_FOR_STATE` dict; update `evaluate()` to return `candidate_agents=[]` (registry lookup happens in dispatcher, not engine); update all WAIT/BLOCK returns that previously set `assigned_agent` to use `candidate_agents=[]`
- [ ] T010 [US1] Update `services/orchestrator/src/services/orchestrator_service.py`: replace all reads of `fsm_eval.assigned_agent` with appropriate handling of `candidate_agents` (WAIT path: pass `assigned_agent=None`; _run path: remove assumption that FSM sets agent)
- [ ] T011 [US1] Add `_summarize_registry()` helper and inject `[AGENT REGISTRY]` section into `_build_user_message()` in `services/orchestrator/src/services/llm/orchestrator_llm.py` when `registry_yaml` is present in `job_payload`; add `job_payload: dict` parameter to `call_orchestrator_llm()`; update `_SYSTEM_PROMPT` to instruct LLM that `assigned_agent` MUST be a `role_id` from the registry
- [ ] T012 [P] [US1] Update existing FSM engine unit tests in `services/orchestrator/tests/unit/test_fsm_engine.py`: remove all assertions on `assigned_agent`, add assertions on `candidate_agents` being a list; add test `test_agent_for_state_does_not_exist` confirming the symbol is gone; add tests for `implementation` (multiple candidates) and `architecture_review` candidates
- [ ] T013 [P] [US1] Update existing orchestrator LLM unit tests in `services/orchestrator/tests/unit/test_orchestrator_llm.py` for the new `job_payload` parameter and registry section inclusion

**Checkpoint**: All existing orchestrator tests pass with updated signatures; `AGENT_FOR_STATE` is gone; FSM evaluation produces `candidate_agents`.

---

## Phase 4: User Story 2 — Brainstorm Participant Discovery (Priority: P2)

**Goal**: `get_brainstorm_participants()` correctly includes cross-cutting agents; brainstorm coordinator uses registry to determine participants instead of the hardcoded config string.

**Independent Test**: Call `registry.get_brainstorm_participants("architecture_review")` and assert both `software-architect` and `security-architect` are returned. Verify `brainstorm_agents_list` is now derived from the registry for architecture_review sessions.

### Implementation for User Story 2

- [ ] T014 [US2] Update brainstorm routing in `services/agent-dispatcher/src/services/dispatcher_service.py`: replace hardcoded `needs_brainstorm` check and `settings.brainstorm_agents_list` lookup with registry-driven participant discovery via `get_registry().get_brainstorm_participants(ticket.fsm_status)`; pass participant list to `BrainstormCoordinator`
- [ ] T015 [US2] Update `BrainstormCoordinator.run_brainstorm()` in `services/agent-dispatcher/src/services/brainstorm_coordinator.py` to accept a `participants: list[str]` parameter instead of reading `settings.brainstorm_agents_list` internally
- [ ] T016 [P] [US2] Add unit tests for brainstorm participant discovery in `services/agent-dispatcher/tests/unit/test_capability_registry.py` (extend existing test file): `test_get_brainstorm_participants_architecture_review_includes_security`, `test_get_brainstorm_participants_single_owner_no_also_for`

**Checkpoint**: Architecture review brainstorm includes `security-architect` in participant list; `brainstorm_agents` config string is no longer the sole source of brainstorm participants.

---

## Phase 5: User Story 3 — Registry Delivered to Orchestrator (Priority: P2)

**Goal**: Every job trigger payload from agent-dispatcher includes `registry_yaml`; orchestrator validates `assigned_agent` against the registry and invokes fallback on unknown roles.

**Independent Test**: Inspect a job trigger payload and confirm `registry_yaml` key is present and contains valid YAML with all 10 agents. Trigger a synthetic job where LLM returns an unknown role and verify the fallback selector is invoked.

### Implementation for User Story 3

- [ ] T017 [US3] Update `Reporter._trigger_orchestrator()` in `services/agent-dispatcher/src/services/reporter.py`: add `registry: CapabilityRegistry` parameter; include `"registry_yaml": registry.to_yaml_string()` in the trigger payload dict
- [ ] T018 [US3] Update all call sites of `reporter.report_result()` in `services/agent-dispatcher/src/services/dispatcher_service.py` to pass the registry instance (obtain via `get_registry()`)
- [ ] T019 [US3] Implement `select_agent()` function in `services/orchestrator/src/services/fsm/agent_selector.py` (full implementation per spec: single-candidate fast path, multi-candidate LLM call, fallback to `candidate_role_ids[0]`, empty-candidates fallback to `"product-manager"`, 10s timeout)
- [ ] T020 [US3] Update `OrchestratorService._run()` in `services/orchestrator/src/services/orchestrator_service.py`: pass `job.payload` to `call_orchestrator_llm()`; after LLM call, validate `decision.decision.assigned_agent` against registry roles parsed from `job.payload.get("registry_yaml", "")`; on invalid role invoke `select_agent()` fallback and patch `decision.decision.assigned_agent`
- [ ] T021 [P] [US3] Write unit tests for `select_agent()` in `services/orchestrator/tests/unit/test_agent_selector.py` (all 7 test cases from spec: single candidate no LLM, empty candidates default, LLM selects backend, LLM selects frontend, invalid LLM response fallback, LLM timeout fallback, LLM API error fallback)
- [ ] T022 [P] [US3] Update reporter unit tests in `services/agent-dispatcher/tests/unit/test_reporter.py` for new `registry` parameter in `report_result()`

**Checkpoint**: Job trigger payloads include `registry_yaml`; unknown role assignments are intercepted and corrected via `select_agent()`; all new unit tests pass.

---

## Phase 6: User Story 4 — Credentials Written Before Agent Spawn (Priority: P3)

**Goal**: `credentials.json` is written to `development/{role_id}/` immediately before every agent spawn.

**Independent Test**: Run a dry-run spawn for role `backend` and verify `development/backend/credentials.json` exists with correct structure; verify `git status` does not show the file as tracked.

### Implementation for User Story 4

- [ ] T023 [US4] Add `get_service_token() -> str` method to `TicketManagerClient` in `services/agent-dispatcher/src/services/tm_client/` (exposes the internally-held `_token` without re-authentication)
- [ ] T024 [US4] Implement `_write_credentials(role_id: str)` async method in `services/agent-dispatcher/src/services/dispatcher_service.py`: fetch token via `TicketManagerClient.get_service_token()`; write `{"host": ..., "token": ..., "role": role_id}` to `development/{role_id}/credentials.json`; create parent directory if needed
- [ ] T025 [US4] Call `await self._write_credentials(agent_id)` in `process_ticket()` in `services/agent-dispatcher/src/services/dispatcher_service.py` immediately before `runner.run()`
- [ ] T026 [P] [US4] Write unit tests for credentials writing in `services/agent-dispatcher/tests/unit/test_dispatcher_credentials.py`: mock `TicketManagerClient.get_service_token()`; verify file is written with correct keys; verify path is `development/{role_id}/credentials.json`

**Checkpoint**: Credentials file written before every agent spawn; file is gitignored; unit tests pass.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Validation, cleanup, and verification across all user stories.

- [ ] T027 [P] Verify `AGENT_FOR_STATE` does not appear anywhere in the codebase (`grep -r "AGENT_FOR_STATE" services/`)
- [ ] T028 [P] Verify all hardcoded underscore role strings are gone from orchestrator and dispatcher source (`grep -r '"project_manager\|software_architect\|security_architect\|code_reviewer"' services/`)
- [ ] T029 Run full unit test suite for both services and confirm ≥80% coverage on new modules (`capability_registry.py`, `agent_selector.py`)
- [ ] T030 [P] Verify `development/**/credentials.json` is correctly matched by `.gitignore` (`git check-ignore -v development/backend/credentials.json`)
- [ ] T031 [P] Confirm `registry.yaml` validates cleanly against schema in `contracts/registry-schema.md` — run a manual `python -c "import yaml; yaml.safe_load(open('development/agents/registry.yaml'))"` sanity check

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — start immediately
- **Phase 2 (Foundational)**: Depends on Phase 1 (registry.yaml must exist for `CapabilityRegistry.load()` to succeed in tests)
- **Phase 3 (US1)**: Depends on Phase 2 (`FSMEvaluation.candidate_agents` shape must be stable)
- **Phase 4 (US2)**: Depends on Phase 2 (uses `get_brainstorm_participants()`)
- **Phase 5 (US3)**: Depends on Phase 2 (needs `to_yaml_string()`) and Phase 3 (needs `candidate_agents` for `select_agent()` fallback path)
- **Phase 6 (US4)**: Depends on Phase 2 (needs `get_registry()` available at startup for credentials path resolution) — otherwise independent
- **Phase 7 (Polish)**: Depends on all phases

### User Story Dependencies

- **US1 (P1)**: Start after Phase 2 — no dependency on other stories
- **US2 (P2)**: Start after Phase 2 — no dependency on US1
- **US3 (P2)**: Start after Phase 2 + US1 complete (needs `candidate_agents` in `FSMEvaluation`)
- **US4 (P3)**: Start after Phase 2 — no dependency on US1/US2/US3

### Within Each Phase

- T009 (FSM engine change) MUST complete before T010 and T011 (callers of `fsm_eval`)
- T005 (CapabilityRegistry class) MUST complete before T007 (lifespan wiring)
- T019 (agent_selector.py) MUST complete before T020 (validation in orchestrator_service)
- T017 (reporter update) MUST complete before T018 (call sites pass registry)
- T023 (get_service_token) MUST complete before T024 (_write_credentials)

### Parallel Opportunities

- T001 (registry.yaml) and T002/T003/T004 (constants/config/gitignore) — all independent
- T008 (capability_registry tests) can be written in parallel with T007 (lifespan wiring)
- T012 and T013 (FSM/LLM test updates) can run in parallel after T009
- T016 (brainstorm tests) runs in parallel with T015 (coordinator update)
- T021 and T022 (selector/reporter tests) run in parallel with T019 and T017

---

## Parallel Example: Phase 1

```bash
# All Phase 1 tasks can run in parallel (different files):
Task T001: Create development/agents/registry.yaml
Task T002: Update services/agent-dispatcher/src/core/constants.py
Task T003: Update services/agent-dispatcher/src/core/config.py
Task T004: Update .gitignore
```

## Parallel Example: Phase 3 (US1)

```bash
# After T009 completes:
Task T010: Update orchestrator_service.py
Task T011: Update orchestrator_llm.py
Task T012: Update test_fsm_engine.py  [parallel with T010/T011]
Task T013: Update test_orchestrator_llm.py  [parallel with T010/T011]
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001–T004)
2. Complete Phase 2: Foundational (T005–T008)
3. Complete Phase 3: US1 (T009–T013)
4. **STOP and VALIDATE**: Verify `AGENT_FOR_STATE` is gone; FSM returns `candidate_agents`; LLM prompt contains `[AGENT REGISTRY]`
5. End-to-end smoke test: trigger a feature ticket and observe correct agent assignment in logs

### Incremental Delivery

1. Phase 1 + Phase 2 → Registry loaded at startup ✓
2. Phase 3 (US1) → Correct agent assigned based on ticket content ✓ (MVP)
3. Phase 4 (US2) → Security architect included in architecture reviews ✓
4. Phase 5 (US3) → Invalid role assignments intercepted and corrected ✓
5. Phase 6 (US4) → Credentials written before every agent spawn ✓
6. Phase 7 (Polish) → Coverage verified, cleanup complete ✓

### Atomic Risk: VALID_AGENT_IDS Migration (T002)

T002 changes the ID format used for whitelist validation. It must be deployed simultaneously with the registry (T001). Any intermediate state where the orchestrator sends hyphenated IDs but the dispatcher still has underscore IDs will cause all agent dispatches to fail. Deploy T001 and T002 together.

---

## Notes

- [P] tasks operate on different files with no shared dependencies — safe to run simultaneously
- [Story] label maps each task to the user story it fulfils for traceability
- T002 and T009 are the two highest-risk changes (whitelist format migration + FSM dataclass change) — validate both with tests before proceeding
- Credentials files (`development/**/credentials.json`) must never appear in `git status` after T004
- The `brainstorm_agents` config string (T003) remains valid as a fallback for non-FSM-state-driven contexts; the registry augments it for architecture_review sessions
